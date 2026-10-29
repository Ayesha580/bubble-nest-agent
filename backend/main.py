"""Bubble Nest - universal AI business agent platform (single-file FastAPI backend).

Database: PostgreSQL via DATABASE_URL (SQLite fallback for local dev). Tables are created on startup.
"""
import os, json, re, socket, ipaddress, time, secrets, hashlib, hmac, uuid
import smtplib, threading, queue
from collections import defaultdict, deque
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
ORIGINS = [o.strip().rstrip("/") for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bubblenest.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER

AWAIT = "Awaiting Customer Confirmation"
STATUSES = ["Draft", AWAIT, "Confirmed", "Accepted by Business", "Preparing or Processing", "Out for Delivery", "Completed", "Cancelled"]
OWNER_STATUSES = STATUSES[2:]
ACTIVE_SQL = "('Completed','Cancelled')"
SOURCES = {"ai": "by dashboard AI", "auto": "by auto agent", "employee": "by employee"}

app = FastAPI(title="Rides AI Business Agent")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
client = AsyncOpenAI(api_key=API_KEY) if API_KEY else None

# ---------------------------------------------------------------- database
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
PG = engine.dialect.name == "postgresql"
PK = "SERIAL PRIMARY KEY" if PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS businesses(id {PK}, widget_id TEXT UNIQUE NOT NULL, profile TEXT NOT NULL, agent TEXT NOT NULL, knowledge TEXT DEFAULT '', created DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS users(id {PK}, biz INTEGER NOT NULL, email TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, pw TEXT NOT NULL, created DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, biz INTEGER NOT NULL, expires DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS items(id {PK}, biz INTEGER NOT NULL, name TEXT NOT NULL, description TEXT DEFAULT '', category TEXT DEFAULT 'General', price DOUBLE PRECISION NOT NULL, available INTEGER DEFAULT 1, stock INTEGER, image TEXT DEFAULT '', created DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS employees(id {PK}, biz INTEGER NOT NULL, name TEXT NOT NULL, email TEXT DEFAULT '', role TEXT DEFAULT 'Staff', created DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS customers(id {PK}, biz INTEGER NOT NULL, name TEXT, contact TEXT, orders_count INTEGER DEFAULT 0, created DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS leads(id {PK}, biz INTEGER NOT NULL, name TEXT, contact TEXT, message TEXT, conv TEXT, created DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, biz INTEGER NOT NULL, channel TEXT, handoff INTEGER DEFAULT 0, handoff_note TEXT DEFAULT '', created DOUBLE PRECISION, updated DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS messages(id {PK}, conv TEXT NOT NULL, biz INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, latency_ms INTEGER, created DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS orders(id {PK}, biz INTEGER NOT NULL, number TEXT DEFAULT '', conv TEXT, customer TEXT, contact TEXT, address TEXT DEFAULT '', fulfillment TEXT, notes TEXT DEFAULT '', subtotal DOUBLE PRECISION, delivery_fee DOUBLE PRECISION, tax DOUBLE PRECISION, total DOUBLE PRECISION, status TEXT NOT NULL, payment_status TEXT DEFAULT 'Unpaid', created DOUBLE PRECISION, confirmed_at DOUBLE PRECISION, assigned_to INTEGER);
CREATE TABLE IF NOT EXISTS order_items(id {PK}, order_id INTEGER NOT NULL, item_id INTEGER, name TEXT, qty INTEGER, price DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS events(id {PK}, biz INTEGER NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, detail TEXT DEFAULT '', created DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS imports(id {PK}, biz INTEGER NOT NULL, url TEXT, status TEXT, text TEXT DEFAULT '', error TEXT DEFAULT '', created DOUBLE PRECISION);
CREATE INDEX IF NOT EXISTS idx_items_biz ON items(biz);
CREATE INDEX IF NOT EXISTS idx_orders_biz ON orders(biz);
CREATE INDEX IF NOT EXISTS idx_orders_conv ON orders(conv);
CREATE INDEX IF NOT EXISTS idx_msgs_conv ON messages(conv);
CREATE INDEX IF NOT EXISTS idx_events_biz ON events(biz);
"""
with engine.begin() as _c:
    for _s in SCHEMA.split(";"):
        if _s.strip():
            _c.execute(text(_s))

# Migrations for databases created before these columns existed.
for _sql in ("ALTER TABLE orders ADD COLUMN assigned_to INTEGER", "ALTER TABLE orders ADD COLUMN email TEXT DEFAULT ''"):
    try:
        with engine.begin() as _c:
            _c.execute(text(_sql))
    except Exception:
        pass  # column already exists


def _norm(a):
    return {k: (int(v) if isinstance(v, bool) else v) for k, v in a.items()}


def q(sql, **a):
    with engine.begin() as c:
        return [dict(r._mapping) for r in c.execute(text(sql), _norm(a))]


def one(sql, **a):
    r = q(sql, **a)
    return r[0] if r else None


def run(sql, **a):
    """INSERT ... RETURNING id -> id; otherwise affected row count."""
    with engine.begin() as c:
        r = c.execute(text(sql), _norm(a))
        return r.scalar() if r.returns_rows else r.rowcount


def ev(biz, kind, title, detail=""):
    run("INSERT INTO events(biz,kind,title,detail,created) VALUES(:b,:k,:t,:d,:c)", b=biz, k=kind, t=title, d=str(detail)[:400], c=time.time())


def audit(biz, title, detail=""):
    ev(biz, "audit", title, detail)


# ---------------------------------------------------------------- email (single worker queue, 3 tries)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAIL_Q = queue.Queue()


def _smtp_deliver(to, subject, body):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = SMTP_FROM, to, subject
    m.set_content(body)
    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(m)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(m)


def _mail_worker():
    while True:
        biz_id, to, subject, body = MAIL_Q.get()
        for attempt in range(3):
            try:
                _smtp_deliver(to, subject, body)
                ev(biz_id, "agent", "Email sent to customer", f"{to}: {subject}"[:300])
                break
            except Exception as e:
                print(f"Email error (try {attempt + 1}): {e}")
                if attempt == 2:
                    ev(biz_id, "error", "Email failed", f"{to}: {str(e)[:250]}")
                else:
                    time.sleep(2 * (attempt + 1))
        MAIL_Q.task_done()


threading.Thread(target=_mail_worker, daemon=True).start()


def send_email(biz_id, to, subject, body):
    to = (to or "").strip()
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        ev(biz_id, "error", "Email not sent", "SMTP settings missing on server")
        return False
    if not EMAIL_RE.match(to):
        ev(biz_id, "error", "Email not sent", "Invalid customer email")
        return False
    MAIL_Q.put((biz_id, to, subject, body))
    return True


def _profile(biz_id):
    b = one("SELECT profile FROM businesses WHERE id=:b", b=biz_id)
    return json.loads(b["profile"]) if b else {}


def email_confirmation(biz_id, o):
    if not o.get("email"):
        return
    p, cur = _profile(biz_id), _profile(biz_id).get("currency", "PKR")
    lines = q("SELECT name,qty,price FROM order_items WHERE order_id=:i ORDER BY id", i=o["id"])
    items = "\n".join(f"  {l['qty']} x {l['name']} - {cur} {l['qty'] * l['price']:g}" for l in lines)
    where = f"Delivery address: {o['address']}" if o["fulfillment"] == "Delivery" else "Pickup from the business"
    send_email(biz_id, o["email"], f"{p.get('name', 'Order')}: order {o['number']} confirmed",
               f"Hi {o.get('customer') or 'there'},\n\nThank you! Your order {o['number']} is confirmed.\n\n"
               f"Items:\n{items}\n\nSubtotal: {cur} {o['subtotal']:g}\nDelivery: {cur} {o['delivery_fee']:g}\nTax: {cur} {o['tax']:g}\n"
               f"Total: {cur} {o['total']:g} (payment: Unpaid)\n\nMethod: {o['fulfillment']}\n{where}\nPhone: {o['contact']}\n\n"
               f"We'll email you at every step.\n\n- {p.get('name', 'The team')}")


STATUS_NOTE = {
    "Confirmed": "Your order has been received and confirmed.",
    "Accepted by Business": "Our team has accepted your order.",
    "Preparing or Processing": "Your order is being prepared.",
    "Out for Delivery": "Your order is on its way to you.",
    "Completed": "Your order has been delivered/completed. Thank you!",
    "Cancelled": "Your order was cancelled. Please contact us if you have questions.",
}


def email_status(biz_id, o, status):
    if not o.get("email"):
        return
    p = _profile(biz_id)
    send_email(biz_id, o["email"], f"{p.get('name', 'Your order')}: order {o['number']} is now {status}",
               f"Hi {o.get('customer') or 'there'},\n\nOrder {o['number']} status: {status}.\n{STATUS_NOTE.get(status, '')}\n\n"
               f"Total: {p.get('currency', 'PKR')} {o['total']:g}\n\n- {p.get('name', 'The team')}")


def patch(table, cols, rid, biz, data):
    data = {k: v for k, v in data.items() if k in cols}
    if not data:
        return
    sets = ",".join(f"{k}=:{k}" for k in data)
    if not run(f"UPDATE {table} SET {sets} WHERE id=:rid AND biz=:biz", rid=rid, biz=biz, **data):
        raise HTTPException(404, "Not found.")


# S and fn MUST be defined before any tool list that uses them.
S = {"type": "string"}


def fn(name, desc, props, req):
    return {"type": "function", "name": name, "description": desc, "parameters": {"type": "object", "properties": props, "required": req}}


hits = defaultdict(deque)


def limit(key, n=20, per=60):
    now, d = time.time(), hits[key]
    while d and now - d[0] > per:
        d.popleft()
    if len(d) >= n:
        raise HTTPException(429, "Too many requests. Please wait a minute.")
    d.append(now)


def ip(request: Request):
    return request.client.host if request.client else "x"


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()


# ---------------------------------------------------------------- defaults & schemas
AGENT_DEFAULT = {
    "enabled": True,
    "instructions": "",
    "tone": "Friendly and professional",
    "language": "Same as the customer",
    "welcome": "",
    "suggestions": [],
    "domains": [],
    "delivery_fee": 0.0,
    "tax_percent": 0.0,
    "fulfillment": ["Pickup", "Delivery"],
    "voice": True,
    "brand_color": "#a523a5",
    "tasks": {
        "enabled": True,
        "allow_status_updates": True,
        "allow_employee_assignment": True,
        "orders": True,
        "handoff": True,
        "auto_process": True,  # confirmed order -> auto accept + assign least busy employee
    },
}


def agent_of(biz):
    agent = {**AGENT_DEFAULT, **json.loads(biz["agent"] or "{}")}
    agent["tasks"] = {**AGENT_DEFAULT["tasks"], **(agent.get("tasks") or {})}
    return agent


class Profile(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: str = Field(default="Other", max_length=60)
    owner: str = Field(default="", max_length=100)
    website: str = Field(default="", max_length=300)
    phone: str = Field(default="", max_length=40)
    address: str = Field(default="", max_length=200)
    hours: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=1000)
    currency: str = Field(default="PKR", max_length=6)
    timezone: str = Field(default="Asia/Karachi", max_length=60)
    support: str = Field(default="", max_length=200)


class Signup(Profile):
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=8, max_length=100)


class Login(BaseModel):
    email: str
    password: str


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=500)
    category: str = Field(default="General", max_length=60)
    price: float = Field(ge=0, le=10_000_000)
    available: bool = True
    stock: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    image: str = Field(default="", max_length=300)


class ItemPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    description: Optional[str] = Field(default=None, max_length=500)
    category: Optional[str] = Field(default=None, max_length=60)
    price: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    available: Optional[bool] = None
    stock: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    image: Optional[str] = Field(default=None, max_length=300)


class EmployeeIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(default="", max_length=200)
    role: str = Field(default="Staff", max_length=60)


class AgentIn(BaseModel):
    enabled: bool = True
    instructions: str = Field(default="", max_length=2000)
    tone: str = Field(default="Friendly and professional", max_length=100)
    language: str = Field(default="Same as the customer", max_length=60)
    welcome: str = Field(default="", max_length=300)
    tasks: dict[str, bool] = {}
    suggestions: list[str] = Field(default_factory=list, max_length=6)
    domains: list[str] = Field(default_factory=list, max_length=20)
    delivery_fee: float = Field(default=0, ge=0, le=1_000_000)
    tax_percent: float = Field(default=0, ge=0, le=100)
    fulfillment: list[str] = Field(default_factory=lambda: ["Pickup", "Delivery"])
    voice: bool = True
    brand_color: str = Field(default="#a523a5", pattern=r"^#[0-9a-fA-F]{6}$")


class TextIn(BaseModel):
    text: str = Field(max_length=8000)


class StatusIn(BaseModel):
    status: str


class AssignIn(BaseModel):
    employee_id: Optional[int] = None


class ChatReq(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: Optional[str] = Field(default=None, max_length=64)


class DashboardAgentReq(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=12)


class OwnerToolReq(BaseModel):
    name: str = Field(max_length=60)
    args: dict = {}


class ConvReq(BaseModel):
    conversation_id: Optional[str] = Field(default=None, max_length=64)


class ToolReq(BaseModel):
    conversation_id: str = Field(max_length=64)
    name: str = Field(max_length=60)
    args: dict = {}


class LogReq(BaseModel):
    conversation_id: str = Field(max_length=64)
    role: str
    content: str = Field(min_length=1, max_length=3000)


# ---------------------------------------------------------------- auth
def new_session(user_id, biz):
    tok = secrets.token_urlsafe(32)
    run("INSERT INTO sessions(token_hash,user_id,biz,expires) VALUES(:h,:u,:b,:e)", h=sha(tok), u=user_id, b=biz, e=time.time() + 30 * 86400)
    return tok


def owner(authorization: str = Header(default="")):
    tok = authorization.removeprefix("Bearer ").strip()
    s = one("SELECT user_id,biz FROM sessions WHERE token_hash=:h AND expires>:n", h=sha(tok), n=time.time()) if tok else None
    if not s:
        raise HTTPException(401, "Please log in again.")
    return s


@app.get("/health")
def health():
    one("SELECT 1 AS ok")
    return {"status": "ok", "database": engine.dialect.name, "api_key_configured": bool(API_KEY), "smtp_configured": bool(SMTP_HOST and SMTP_USER and SMTP_PASS)}


@app.post("/auth/signup")
def signup(body: Signup, request: Request):
    limit(f"auth:{ip(request)}", 10, 60)
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address.")
    if one("SELECT 1 AS x FROM users WHERE email=:e", e=email):
        raise HTTPException(409, "This email already has an account. Please log in.")
    profile = body.model_dump(exclude={"email", "password"})
    profile["email"] = email
    biz = run("INSERT INTO businesses(widget_id,profile,agent,created) VALUES(:w,:p,:a,:c) RETURNING id",
              w="wg_" + secrets.token_hex(8), p=json.dumps(profile), a=json.dumps(AGENT_DEFAULT), c=time.time())
    salt = secrets.token_hex(8)
    uid = run("INSERT INTO users(biz,email,salt,pw,created) VALUES(:b,:e,:s,:p,:c) RETURNING id", b=biz, e=email, s=salt, p=hash_pw(body.password, salt), c=time.time())
    audit(biz, "Workspace created", body.name)
    return {"token": new_session(uid, biz)}


@app.post("/auth/login")
def login(body: Login, request: Request):
    limit(f"auth:{ip(request)}", 10, 60)
    u = one("SELECT * FROM users WHERE email=:e", e=body.email.strip().lower())
    if not u or not hmac.compare_digest(u["pw"], hash_pw(body.password, u["salt"])):
        raise HTTPException(401, "Wrong email or password.")
    return {"token": new_session(u["id"], u["biz"])}


@app.post("/auth/logout")
def logout(authorization: str = Header(default="")):
    run("DELETE FROM sessions WHERE token_hash=:h", h=sha(authorization.removeprefix("Bearer ").strip()))
    return {"ok": True}


# ---------------------------------------------------------------- shared helpers
def order_view(oid):
    o = one("SELECT * FROM orders WHERE id=:i", i=oid)
    if o:
        o["lines"] = q("SELECT name,qty,price FROM order_items WHERE order_id=:i ORDER BY id", i=oid)
    return o


def add_msg(b, conv, role, content, latency=None):
    return run("INSERT INTO messages(conv,biz,role,content,latency_ms,created) VALUES(:c,:b,:r,:t,:l,:n) RETURNING id",
               c=conv, b=b, r=role, t=content, l=latency, n=time.time())


def norm_number(v):
    v = str(v or "").strip().upper()
    return f"ORD-{int(v):05d}" if v.isdigit() else v


def find_employee(biz_id, name):
    """Find one employee by (partial) name. Returns (employee, error)."""
    n = str(name or "").strip().lower()
    if not n:
        return None, "Employee name is required."
    rows = q("SELECT * FROM employees WHERE biz=:b AND LOWER(name)=:n", b=biz_id, n=n) or \
        q("SELECT * FROM employees WHERE biz=:b AND LOWER(name) LIKE :n LIMIT 5", b=biz_id, n=f"%{n}%")
    if not rows:
        return None, "Employee not found."
    if len(rows) > 1:
        return None, "Ambiguous, matches: " + ", ".join(r["name"] for r in rows)
    return rows[0], None


def assign_order(biz_id, o, emp, source="owner"):
    if o["status"] == AWAIT:
        raise ValueError("The customer has not confirmed this order yet.")
    if o["status"] in ("Cancelled", "Completed"):
        raise ValueError(f"A {o['status'].lower()} order cannot be changed.")
    run("UPDATE orders SET assigned_to=:e WHERE id=:i AND biz=:b", e=emp["id"] if emp else None, i=o["id"], b=biz_id)
    audit(biz_id, f"Order {o['number']} assigned to {emp['name'] if emp else 'nobody'}", SOURCES.get(source, "by owner"))
    if emp and o["status"] == "Confirmed":  # assigning = employee accepted -> order moves forward
        apply_status(biz_id, one("SELECT * FROM orders WHERE id=:i", i=o["id"]), "Accepted by Business", source)


def apply_status(biz_id, o, status, source="owner"):
    if status not in OWNER_STATUSES:
        raise ValueError("Invalid status. Allowed: " + ", ".join(OWNER_STATUSES))
    if o["status"] == AWAIT:
        raise ValueError("The customer has not confirmed this order yet.")
    if o["status"] in ("Cancelled", "Completed"):
        raise ValueError(f"A {o['status'].lower()} order cannot be changed.")
    if status == o["status"]:
        return
    with engine.begin() as c:
        c.execute(text("UPDATE orders SET status=:s WHERE id=:i AND biz=:b"), {"s": status, "i": o["id"], "b": biz_id})
        if status == "Cancelled":
            for l in c.execute(text("SELECT item_id,qty FROM order_items WHERE order_id=:i"), {"i": o["id"]}).mappings().all():
                c.execute(text("UPDATE items SET stock=stock+:q WHERE id=:i AND biz=:b AND stock IS NOT NULL"), {"q": l["qty"], "i": l["item_id"], "b": biz_id})
    audit(biz_id, f"Order {o['number']} set to {status}", SOURCES.get(source, "by owner"))
    if o.get("conv"):
        msg = (f"Update on your order {o['number']}: it has been delivered. Thank you!"
                if status == "Completed" else
                f"Update on your order {o['number']}: it is now \"{status}\".")
        add_msg(biz_id, o["conv"], "business", msg)
    email_status(biz_id, o, status)


def auto_process(biz_id, oid):
    """Auto agent: accept a newly confirmed order and assign it to the least busy employee."""
    biz = one("SELECT * FROM businesses WHERE id=:b", b=biz_id)
    if not biz or not agent_of(biz)["tasks"].get("auto_process", True):
        return
    o = one("SELECT * FROM orders WHERE id=:i AND biz=:b", i=oid, b=biz_id)
    if not o or o["status"] != "Confirmed":
        return
    emps = q(f"SELECT e.*, (SELECT COUNT(*) FROM orders x WHERE x.assigned_to=e.id AND x.status NOT IN {ACTIVE_SQL}) AS active "
             "FROM employees e WHERE e.biz=:b ORDER BY active, e.id", b=biz_id)
    try:
        if emps:
            assign_order(biz_id, o, emps[0], "auto")
            ev(biz_id, "agent", "Auto agent accepted & assigned order", f"{o['number']} -> {emps[0]['name']}")
        else:
            apply_status(biz_id, o, "Accepted by Business", "auto")
            ev(biz_id, "agent", "Auto agent accepted order (no employees to assign)", o["number"])
    except Exception as e:
        ev(biz_id, "error", "Auto agent failed", str(e)[:300])


# ------------------------------------------------ dashboard AI assistant (business side)
DASHBOARD_AGENT_TOOLS = [
    fn("search_orders", "List/search orders. Empty query = latest. Optional exact status filter. Includes assigned_to (employee id or null).", {"query": S, "status": S}, []),
    fn("update_order_status", "Change an order's status. Only when the owner clearly asks. Not for orders awaiting customer confirmation.", {"number": S, "status": S}, ["number", "status"]),
    fn("list_conversations", "List recent customer conversations. only_handoff=true shows chats needing a human.", {"only_handoff": {"type": "boolean"}}, []),
    fn("read_customer_conversation", "Read a conversation transcript and its orders.", {"conversation_id": S}, ["conversation_id"]),
    fn("reply_to_customer", "Post a reply from the business into a customer's chat window.", {"conversation_id": S, "message": S}, ["conversation_id", "message"]),
    fn("resolve_handoff", "Mark a human-handoff conversation as resolved.", {"conversation_id": S}, ["conversation_id"]),
    fn("update_item", "Update a product/service by name: price, availability or stock.",
       {"name": S, "price": {"type": "number"}, "available": {"type": "boolean"}, "stock": {"type": "integer"}}, ["name"]),
    fn("get_performance", "Performance report: orders/revenue (7/30 days), orders by status, top items, team workload, handoffs, AI response time.", {}, []),
    fn("email_customer", "Send a custom email to the customer of an order.", {"number": S, "message": S}, ["number", "message"]),
    fn("list_employees", "List team members with their active order counts.", {}, []),
    fn("assign_order", "Assign an order to an employee by name (empty string = unassign). Only when the owner clearly asks.", {"number": S, "employee": S}, ["number", "employee"]),
]
DASH_TOOL_NAMES = {t["name"] for t in DASHBOARD_AGENT_TOOLS}


def dashboard_agent_tool(biz_id, name, args):
    """Execute dashboard AI actions only within the authenticated business."""
    args = args if isinstance(args, dict) else {}

    if name == "search_orders":
        query, status = str(args.get("query", "")).strip()[:100], str(args.get("status", "")).strip()
        conds, p = ["biz=:b"], {"b": biz_id}
        if query:
            conds.append("(LOWER(number) LIKE :k OR LOWER(customer) LIKE :k OR LOWER(contact) LIKE :k OR LOWER(status) LIKE :k)")
            p["k"] = f"%{query.lower()}%"
        if status:
            conds.append("status=:st")
            p["st"] = status
        rows = q("SELECT id,number,customer,contact,address,notes,status,fulfillment,subtotal,delivery_fee,tax,total,payment_status,created,conv,assigned_to "
                 f"FROM orders WHERE {' AND '.join(conds)} ORDER BY id DESC LIMIT 20", **p)
        for o in rows:
            o["lines"] = q("SELECT name,qty,price FROM order_items WHERE order_id=:i ORDER BY id", i=o["id"])
        return {"ok": True, "count": len(rows), "orders": rows}

    if name == "update_order_status":
        number, status = norm_number(args.get("number")), str(args.get("status", "")).strip()
        order = one("SELECT * FROM orders WHERE biz=:b AND number=:n", b=biz_id, n=number)
        if not order:
            return {"ok": False, "error": "Order not found."}
        old = order["status"]
        try:
            apply_status(biz_id, order, status, "ai")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        ev(biz_id, "agent", "Order status updated by AI", f"{number}: {old} -> {status}")
        return {"ok": True, "number": number, "old_status": old, "status": status,
                "note": "Status updated. Customer notified in chat and by email (if they gave one)."}

    if name == "list_conversations":
        extra = " AND c.handoff=1" if args.get("only_handoff") else ""
        rows = q("SELECT c.id,c.channel,c.handoff,c.handoff_note,c.updated,"
                 "(SELECT content FROM messages m WHERE m.conv=c.id ORDER BY m.id DESC LIMIT 1) AS last_message "
                 f"FROM conversations c WHERE c.biz=:b{extra} ORDER BY c.updated DESC LIMIT 15", b=biz_id)
        return {"ok": True, "conversations": rows}

    if name == "read_customer_conversation":
        cid = str(args.get("conversation_id", "")).strip()[:64]
        conv = one("SELECT * FROM conversations WHERE id=:i AND biz=:b", i=cid, b=biz_id)
        if not conv:
            return {"ok": False, "error": "Conversation not found."}
        msgs = q("SELECT role,content,created FROM messages WHERE conv=:c AND biz=:b ORDER BY id LIMIT 100", c=cid, b=biz_id)
        orders = q("SELECT number,status,total,customer,contact FROM orders WHERE conv=:c AND biz=:b ORDER BY id", c=cid, b=biz_id)
        return {"ok": True, "conversation_id": cid, "handoff": conv["handoff"] == 1, "handoff_note": conv["handoff_note"], "orders": orders, "messages": msgs}

    if name == "reply_to_customer":
        cid, message = str(args.get("conversation_id", "")).strip()[:64], str(args.get("message", "")).strip()
        if not message or len(message) > 2000:
            return {"ok": False, "error": "Reply must contain between 1 and 2000 characters."}
        if not one("SELECT id FROM conversations WHERE id=:i AND biz=:b", i=cid, b=biz_id):
            return {"ok": False, "error": "Conversation not found."}
        add_msg(biz_id, cid, "business", message)
        run("UPDATE conversations SET updated=:t WHERE id=:i AND biz=:b", t=time.time(), i=cid, b=biz_id)
        ev(biz_id, "agent", "Business reply sent", f"Conversation {cid[:8]}")
        return {"ok": True, "conversation_id": cid, "message": message,
                "note": "Posted in the customer's chat window only. No email/SMS/WhatsApp sent."}

    if name == "resolve_handoff":
        cid = str(args.get("conversation_id", "")).strip()[:64]
        if not run("UPDATE conversations SET handoff=2 WHERE id=:i AND biz=:b AND handoff=1", i=cid, b=biz_id):
            return {"ok": False, "error": "No open handoff found for that conversation."}
        audit(biz_id, "Human handoff resolved", cid[:8])
        return {"ok": True}

    if name == "update_item":
        n = str(args.get("name", "")).strip().lower()
        rows = q("SELECT * FROM items WHERE biz=:b AND LOWER(name)=:n", b=biz_id, n=n) or \
            q("SELECT * FROM items WHERE biz=:b AND LOWER(name) LIKE :n LIMIT 5", b=biz_id, n=f"%{n}%")
        if len(rows) != 1:
            return {"ok": False, "error": "Item not found." if not rows else "Ambiguous, matches: " + ", ".join(r["name"] for r in rows)}
        upd = {}
        if args.get("price") is not None:
            if not 0 <= float(args["price"]) <= 10_000_000:
                return {"ok": False, "error": "Invalid price."}
            upd["price"] = float(args["price"])
        if args.get("available") is not None:
            upd["available"] = bool(args["available"])
        if args.get("stock") is not None:
            if not 0 <= int(args["stock"]) <= 1_000_000:
                return {"ok": False, "error": "Invalid stock."}
            upd["stock"] = int(args["stock"])
        if not upd:
            return {"ok": False, "error": "Nothing to update."}
        patch("items", {"price", "available", "stock"}, rows[0]["id"], biz_id, upd)
        audit(biz_id, "Item updated by AI", f"{rows[0]['name']}: {upd}")
        return {"ok": True, "item": rows[0]["name"], "updated": upd}

    if name == "list_employees":
        rows = q("SELECT e.id,e.name,e.role,e.email,"
                 f"(SELECT COUNT(*) FROM orders o WHERE o.assigned_to=e.id AND o.status NOT IN {ACTIVE_SQL}) AS active_orders "
                 "FROM employees e WHERE e.biz=:b ORDER BY e.name", b=biz_id)
        return {"ok": True, "employees": rows}

    if name == "assign_order":
        number = norm_number(args.get("number"))
        order = one("SELECT * FROM orders WHERE biz=:b AND number=:n", b=biz_id, n=number)
        if not order:
            return {"ok": False, "error": "Order not found."}
        emp_name, emp = str(args.get("employee", "")).strip(), None
        if emp_name:
            emp, err = find_employee(biz_id, emp_name)
            if err:
                return {"ok": False, "error": err}
        try:
            assign_order(biz_id, order, emp, "ai")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        ev(biz_id, "agent", "Order assigned by AI", f"{number} -> {emp['name'] if emp else 'unassigned'}")
        return {"ok": True, "number": number, "assigned_to": emp["name"] if emp else None,
                "note": "Saved in the dashboard. The employee is not notified outside it."}

    if name == "get_performance":
        now = time.time()

        def agg(days):
            r = one("SELECT COUNT(*) AS n, COALESCE(SUM(total),0) AS v FROM orders WHERE biz=:b AND confirmed_at>:t AND status<>'Cancelled'", b=biz_id, t=now - days * 86400)
            return {"orders": r["n"], "value": r["v"]}
        by = {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) AS n FROM orders WHERE biz=:b GROUP BY status", b=biz_id)}
        top = q("SELECT oi.name, SUM(oi.qty) AS qty FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE o.biz=:b AND o.status NOT IN ('Cancelled',:aw) GROUP BY oi.name ORDER BY qty DESC LIMIT 5", b=biz_id, aw=AWAIT)
        team = q("SELECT e.name, e.role, "
                 f"SUM(CASE WHEN o.status NOT IN {ACTIVE_SQL} THEN 1 ELSE 0 END) AS active, "
                 "SUM(CASE WHEN o.status='Completed' THEN 1 ELSE 0 END) AS completed "
                 "FROM employees e LEFT JOIN orders o ON o.assigned_to=e.id WHERE e.biz=:b GROUP BY e.id, e.name, e.role", b=biz_id)
        cv = one("SELECT COUNT(*) AS n, SUM(CASE WHEN handoff=1 THEN 1 ELSE 0 END) AS open_h FROM conversations WHERE biz=:b", b=biz_id)
        lat = one("SELECT AVG(latency_ms) AS a FROM messages WHERE biz=:b AND role='assistant' AND latency_ms IS NOT NULL", b=biz_id)
        unassigned = one(f"SELECT COUNT(*) AS n FROM orders WHERE biz=:b AND assigned_to IS NULL AND status NOT IN ('Completed','Cancelled',:aw)", b=biz_id, aw=AWAIT)["n"]
        return {"ok": True, "last_7_days": agg(7), "last_30_days": agg(30), "orders_by_status": by, "top_items": top, "team": team,
                "conversations": cv["n"], "open_handoffs": cv["open_h"] or 0, "unassigned_active_orders": unassigned,
                "avg_ai_response_ms": round(lat["a"]) if lat and lat["a"] else None}

    if name == "email_customer":
        number = norm_number(args.get("number"))
        order = one("SELECT * FROM orders WHERE biz=:b AND number=:n", b=biz_id, n=number)
        msg = str(args.get("message", "")).strip()[:1500]
        if not order:
            return {"ok": False, "error": "Order not found."}
        if not order.get("email"):
            return {"ok": False, "error": "This customer did not provide an email address."}
        if not msg:
            return {"ok": False, "error": "Message is empty."}
        p = _profile(biz_id)
        if not send_email(biz_id, order["email"], f"{p.get('name', 'Update')}: about your order {number}", f"Hi {order['customer']},\n\n{msg}\n\n- {p.get('name', '')}"):
            return {"ok": False, "error": "Email is not configured on the server or the address is invalid."}
        return {"ok": True, "emailed_to": order["email"]}

    return {"ok": False, "error": "Unknown assistant action."}


def dashboard_prompt(biz_id, voice=False):
    """One short prompt shared by the dashboard text chat and voice call."""
    profile = _profile(biz_id)
    snap = {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) AS n FROM orders WHERE biz=:b GROUP BY status", b=biz_id)}
    handoffs = one("SELECT COUNT(*) AS n FROM conversations WHERE biz=:b AND handoff=1", b=biz_id)["n"]
    unassigned = one("SELECT COUNT(*) AS n FROM orders WHERE biz=:b AND assigned_to IS NULL AND status NOT IN ('Completed','Cancelled',:aw)", b=biz_id, aw=AWAIT)["n"]
    try:
        now = datetime.now(ZoneInfo(profile.get("timezone") or "UTC"))
    except Exception:
        now = datetime.now(timezone.utc)
    voice_rules = ("\nVOICE: speak in short sentences, give only the top 3 items and offer more. Speech can be misheard: before any change "
                   "(status, assign, price, stock, reply, email) say in one sentence what you will do and wait for a yes, unless the owner "
                   "was fully explicit (order number + action). Read order numbers digit by digit.") if voice else ""
    return f"""You are the dashboard AI assistant for "{profile.get('name', 'this business')}". You work for the owner/staff. Time: {now.strftime('%a %d %b %Y, %I:%M %p')}. Currency: {profile.get('currency', 'PKR')}.

Flow: customer confirms order -> Confirmed -> Accepted by Business -> Preparing or Processing -> Out for Delivery -> Completed (or Cancelled).
With auto-processing on, confirmed orders are accepted and assigned to the least busy employee automatically. Only the owner sets "Out for Delivery"; the assigned employee then marks it delivered (Completed). Assigning a Confirmed order accepts it. Every status change notifies the customer in chat and by email.

Rules:
- Use tools for facts about orders, employees, customers, prices and stock; never guess or invent them. Report exactly what tools return.
- You may also answer ANY other question directly without tools: general business advice, marketing, writing messages, calculations, explanations or casual conversation. Never refuse a normal question just because it is not about orders.
- Change status/assignments/prices/stock, reply to or email customers, resolve handoffs ONLY when the owner clearly asks; if unclear, ask one short question.
- Never touch orders awaiting customer confirmation. Employees are not notified outside the dashboard.
- Performance/team/"how are we doing": call get_performance first, then give a brief summary and 2-3 suggestions using only tool numbers.
- "Least busy": list_employees, then assign_order. "Accept all new": search Confirmed orders, update each, report each result.
- Mention anything needing attention (unassigned orders, open handoffs).
- Be concise. Reply in the owner's language (English, Urdu, Roman Urdu).{voice_rules}

Snapshot: orders by status {json.dumps(snap)}; unassigned active orders {unassigned}; handoffs {handoffs}.
Statuses: {", ".join(OWNER_STATUSES)}.
Business: {json.dumps(profile, ensure_ascii=False)[:1200]}"""


@app.post("/me/agent/chat")
async def dashboard_agent_chat(body: DashboardAgentReq, s=Depends(owner)):
    if not client:
        raise HTTPException(503, "AI is not configured. Add OPENAI_API_KEY to the backend environment.")
    biz_id = s["biz"]
    history = [{"role": i["role"], "content": i["content"][:2000]} for i in body.history[-12:]
               if isinstance(i, dict) and i.get("role") in ("user", "assistant") and isinstance(i.get("content"), str) and i["content"].strip()]
    instructions = dashboard_prompt(biz_id)
    messages = history + [{"role": "user", "content": body.message}]
    actions, reply = [], "Sorry, I couldn't complete that request. Please try again."
    try:
        for _ in range(10):
            response = await client.responses.create(model=MODEL, instructions=instructions, input=messages, tools=DASHBOARD_AGENT_TOOLS, max_output_tokens=1200)
            calls = [i for i in response.output if i.type == "function_call"]
            if not calls:
                reply = response.output_text or reply
                break
            messages += response.output
            for call in calls:
                try:
                    args = json.loads(call.arguments)
                except (ValueError, TypeError):
                    args = {}
                try:
                    result = dashboard_agent_tool(biz_id, call.name, args)
                except Exception as e:
                    ev(biz_id, "error", f"Dashboard tool failed: {call.name}", str(e)[:200])
                    result = {"ok": False, "error": "The action could not be completed."}
                actions.append({"tool": call.name, "ok": bool(result.get("ok")), "result": result})
                messages.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result, ensure_ascii=False, default=str)})
    except Exception as exc:
        print(f"Dashboard AI error: {exc}")
        ev(biz_id, "error", "Dashboard AI request failed", str(exc)[:300])
        raise HTTPException(502, "The dashboard assistant is temporarily unavailable.")
    return {"reply": reply, "actions": actions}


@app.post("/me/agent/tool")
def dashboard_voice_tool(body: OwnerToolReq, s=Depends(owner)):
    """Dashboard voice call runs the same tools as the text assistant."""
    limit(f"dtool:{s['biz']}", 60, 60)
    if body.name not in DASH_TOOL_NAMES:
        return {"result": {"ok": False, "error": "Unknown action."}}
    try:
        result = dashboard_agent_tool(s["biz"], body.name, body.args)
    except Exception as e:
        ev(s["biz"], "error", f"Dashboard voice tool failed: {body.name}", str(e)[:200])
        result = {"ok": False, "error": "The action could not be completed."}
    return {"result": result}


@app.post("/me/agent/voice/session")
async def dashboard_voice_session(s=Depends(owner)):
    limit(f"dvoice:{s['biz']}", 6, 60)
    if not API_KEY:
        raise HTTPException(503, "Voice is not available. Add OPENAI_API_KEY to the backend.")
    session = {"type": "realtime", "model": REALTIME_MODEL, "instructions": dashboard_prompt(s["biz"], voice=True), "tools": DASHBOARD_AGENT_TOOLS,
              "audio": {"input": {"transcription": {"model": "gpt-4o-mini-transcribe"}}, "output": {"voice": "marin"}}}
    try:
        async with httpx.AsyncClient(timeout=20) as h:
            r = await h.post("https://api.openai.com/v1/realtime/client_secrets", headers={"Authorization": f"Bearer {API_KEY}"}, json={"session": session})
        r.raise_for_status()
        secret = r.json()["value"]
    except Exception as exc:
        print(f"Dashboard realtime error: {exc}")
        ev(s["biz"], "error", "Dashboard voice session failed", str(exc)[:300])
        raise HTTPException(502, "Voice is unavailable right now. You can keep using text.")
    return {"client_secret": secret}


# ---------------------------------------------------------------- owner dashboard API
@app.get("/me/state")
def state(s=Depends(owner)):
    b = s["biz"]
    biz = one("SELECT * FROM businesses WHERE id=:b", b=b)
    orders = q("SELECT * FROM orders WHERE biz=:b ORDER BY id DESC LIMIT 300", b=b)
    lines = defaultdict(list)
    for l in q("SELECT order_id,name,qty,price FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE biz=:b)", b=b):
        lines[l["order_id"]].append(l)
    for o in orders:
        o["lines"] = lines[o["id"]]
    cv = one("SELECT COUNT(*) AS n, SUM(CASE WHEN handoff>0 THEN 1 ELSE 0 END) AS h FROM conversations WHERE biz=:b", b=b)
    lat = one("SELECT AVG(latency_ms) AS a FROM messages WHERE biz=:b AND role='assistant' AND latency_ms IS NOT NULL", b=b)
    by = {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) AS n FROM orders WHERE biz=:b GROUP BY status", b=b)}
    done = one("SELECT COALESCE(SUM(total),0) AS v FROM orders WHERE biz=:b AND status='Completed'", b=b)["v"]
    return {
        "widget_id": biz["widget_id"], "profile": json.loads(biz["profile"]), "agent": agent_of(biz), "knowledge": biz["knowledge"],
        "items": q("SELECT * FROM items WHERE biz=:b ORDER BY id DESC", b=b),
        "employees": q(f"SELECT e.*, (SELECT COUNT(*) FROM orders o WHERE o.assigned_to=e.id AND o.status NOT IN {ACTIVE_SQL}) AS active_orders FROM employees e WHERE e.biz=:b ORDER BY e.id DESC", b=b),
        "customers": q("SELECT * FROM customers WHERE biz=:b ORDER BY id DESC LIMIT 300", b=b),
        "orders": orders, "imports": q("SELECT id,url,status,text,error,created FROM imports WHERE biz=:b ORDER BY id DESC LIMIT 5", b=b),
        "conversations": q("SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conv=c.id) AS msgs FROM conversations c WHERE biz=:b ORDER BY updated DESC LIMIT 60", b=b),
        "events": q("SELECT * FROM events WHERE biz=:b ORDER BY id DESC LIMIT 120", b=b),
        "metrics": {"conversations": cv["n"], "handoffs": cv["h"] or 0, "orders_by_status": by, "completed_value": done,
                    "avg_latency_ms": round(lat["a"]) if lat and lat["a"] else None},
    }


@app.put("/me/profile")
def update_profile(body: Profile, s=Depends(owner)):
    biz = one("SELECT profile FROM businesses WHERE id=:b", b=s["biz"])
    run("UPDATE businesses SET profile=:p WHERE id=:b", p=json.dumps({**json.loads(biz["profile"]), **body.model_dump()}), b=s["biz"])
    audit(s["biz"], "Business profile updated")
    return {"ok": True}


@app.put("/me/agent")
def update_agent(body: AgentIn, s=Depends(owner)):
    d = body.model_dump()
    d["tasks"] = {k: bool(d["tasks"].get(k, False)) for k in AGENT_DEFAULT["tasks"]}
    d["suggestions"] = [x.strip()[:100] for x in d["suggestions"] if x.strip()]
    d["fulfillment"] = [f for f in d["fulfillment"] if f in ("Pickup", "Delivery", "Dine-in", "On-site", "Online")] or ["Pickup"]
    d["domains"] = [re.sub(r"^https?://|/.*$", "", x.strip().lower()).split(":")[0] for x in d["domains"] if x.strip()]
    run("UPDATE businesses SET agent=:a WHERE id=:b", a=json.dumps(d), b=s["biz"])
    audit(s["biz"], "AI agent settings updated", "enabled" if d["enabled"] else "disabled")
    return {"ok": True}


@app.put("/me/knowledge")
def save_knowledge(body: TextIn, s=Depends(owner)):
    run("UPDATE businesses SET knowledge=:k WHERE id=:b", k=body.text, b=s["biz"])
    audit(s["biz"], "Knowledge base updated")
    return {"ok": True}


@app.post("/me/items")
def add_item(body: ItemIn, s=Depends(owner)):
    d = body.model_dump()
    iid = run("INSERT INTO items(biz,name,description,category,price,available,stock,image,created) VALUES(:biz,:name,:description,:category,:price,:available,:stock,:image,:c) RETURNING id",
              biz=s["biz"], c=time.time(), **d)
    audit(s["biz"], "Item added", d["name"])
    return {"id": iid}


@app.patch("/me/items/{rid}")
def edit_item(rid: int, body: ItemPatch, s=Depends(owner)):
    patch("items", {"name", "description", "category", "price", "available", "stock", "image"}, rid, s["biz"], body.model_dump(exclude_unset=True))
    audit(s["biz"], "Item updated", f"#{rid}")
    return {"ok": True}


@app.delete("/me/items/{rid}")
def del_item(rid: int, s=Depends(owner)):
    run("DELETE FROM items WHERE id=:i AND biz=:b", i=rid, b=s["biz"])
    audit(s["biz"], "Item deleted", f"#{rid}")
    return {"ok": True}


@app.post("/me/employees")
def add_employee(body: EmployeeIn, s=Depends(owner)):
    rid = run("INSERT INTO employees(biz,name,email,role,created) VALUES(:b,:n,:e,:r,:c) RETURNING id", b=s["biz"], n=body.name, e=body.email, r=body.role, c=time.time())
    audit(s["biz"], "Team member added", body.name)
    return {"id": rid}


@app.delete("/me/employees/{rid}")
def del_employee(rid: int, s=Depends(owner)):
    run("UPDATE orders SET assigned_to=NULL WHERE assigned_to=:i AND biz=:b", i=rid, b=s["biz"])
    run("DELETE FROM employees WHERE id=:i AND biz=:b", i=rid, b=s["biz"])
    audit(s["biz"], "Team member removed", f"#{rid}")
    return {"ok": True}


@app.patch("/me/orders/{oid}")
def set_status(oid: int, body: StatusIn, s=Depends(owner)):
    o = one("SELECT * FROM orders WHERE id=:i AND biz=:b", i=oid, b=s["biz"])
    if not o:
        raise HTTPException(404, "Order not found.")
    try:
        apply_status(s["biz"], o, body.status)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.patch("/me/orders/{oid}/assign")
def set_assignee(oid: int, body: AssignIn, s=Depends(owner)):
    o = one("SELECT * FROM orders WHERE id=:i AND biz=:b", i=oid, b=s["biz"])
    if not o:
        raise HTTPException(404, "Order not found.")
    emp = None
    if body.employee_id:
        emp = one("SELECT * FROM employees WHERE id=:i AND biz=:b", i=body.employee_id, b=s["biz"])
        if not emp:
            raise HTTPException(404, "Employee not found.")
    try:
        assign_order(s["biz"], o, emp)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.patch("/me/orders/{oid}/delivered")
def mark_delivered(oid: int, s=Depends(owner)):
    """Employee side: mark an Out for Delivery order as delivered (Completed)."""
    o = one("SELECT * FROM orders WHERE id=:i AND biz=:b", i=oid, b=s["biz"])
    if not o:
        raise HTTPException(404, "Order not found.")
    if not o["assigned_to"]:
        raise HTTPException(409, "This order has no assigned employee.")
    if o["status"] != "Out for Delivery":
        raise HTTPException(409, "The owner must set the order to Out for Delivery first.")
    try:
        apply_status(s["biz"], o, "Completed", "employee")
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.get("/me/conversations/{cid}")
def conversation(cid: str, s=Depends(owner)):
    c = one("SELECT * FROM conversations WHERE id=:i AND biz=:b", i=cid, b=s["biz"])
    if not c:
        raise HTTPException(404, "Conversation not found.")
    c["messages"] = q("SELECT role,content,latency_ms,created FROM messages WHERE conv=:c ORDER BY id", c=cid)
    return c


@app.post("/me/conversations/{cid}/resolve")
def resolve_handoff(cid: str, s=Depends(owner)):
    run("UPDATE conversations SET handoff=2 WHERE id=:i AND biz=:b AND handoff=1", i=cid, b=s["biz"])
    audit(s["biz"], "Human handoff resolved", cid[:8])
    return {"ok": True}


@app.post("/me/import")
async def import_site(s=Depends(owner)):
    b = s["biz"]
    url = _profile(b).get("website", "")
    u, err, txt = urlparse(url), "", ""
    if u.scheme not in ("http", "https") or not u.hostname:
        raise HTTPException(400, "Add a full website URL (https://...) in Business Profile first.")
    try:
        for info in socket.getaddrinfo(u.hostname, None):
            if not ipaddress.ip_address(info[4][0]).is_global:
                raise HTTPException(400, "This URL is not allowed.")
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as h:
            r = await h.get(url, headers={"User-Agent": "BubbleNestBot/1.0"})
        if r.status_code >= 400:
            err = f"The website answered with HTTP {r.status_code}."
        else:
            html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", r.text)
            txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()[:6000]
            if not txt:
                err = "No readable text found on this page."
    except HTTPException:
        raise
    except (socket.gaierror, httpx.HTTPError):
        err = "Could not open this website."
    iid = run("INSERT INTO imports(biz,url,status,text,error,created) VALUES(:b,:u,:s,:t,:e,:c) RETURNING id", b=b, u=url, s="failed" if err else "review", t=txt, e=err, c=time.time())
    if err:
        ev(b, "error", "Website import failed", err)
        raise HTTPException(502, err)
    audit(b, "Website imported for review", f"{len(txt)} characters")
    return {"id": iid}


@app.post("/me/import/{iid}/publish")
def publish_import(iid: int, body: TextIn, s=Depends(owner)):
    b = s["biz"]
    if not one("SELECT 1 AS x FROM imports WHERE id=:i AND biz=:b AND status='review'", i=iid, b=b):
        raise HTTPException(404, "Import not found.")
    cur = one("SELECT knowledge FROM businesses WHERE id=:b", b=b)["knowledge"] or ""
    run("UPDATE businesses SET knowledge=:k WHERE id=:b", k=cur.split("\n\n[Website]")[0] + "\n\n[Website]\n" + body.text.strip(), b=b)
    run("UPDATE imports SET status='published', text=:t WHERE id=:i", t=body.text, i=iid)
    audit(b, "Website information published to the agent")
    return {"ok": True}


@app.delete("/me/import/{iid}")
def discard_import(iid: int, s=Depends(owner)):
    run("DELETE FROM imports WHERE id=:i AND biz=:b", i=iid, b=s["biz"])
    return {"ok": True}


@app.delete("/me")
def delete_account(s=Depends(owner)):
    b = s["biz"]
    run("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE biz=:b)", b=b)
    for t in ("orders", "items", "employees", "customers", "leads", "messages", "conversations", "events", "imports", "sessions", "users"):
        run(f"DELETE FROM {t} WHERE biz=:b", b=b)
    run("DELETE FROM businesses WHERE id=:b", b=b)
    return {"ok": True}


# ---------------------------------------------------------------- public widget plumbing
def widget_biz(wid, request: Request):
    biz = one("SELECT * FROM businesses WHERE widget_id=:w", w=wid)
    if not biz:
        raise HTTPException(404, "Unknown widget.")
    domains = agent_of(biz)["domains"]
    if domains:
        host = (request.headers.get("x-embed-host") or "").lower().split(":")[0]
        ok = any(host == d or host.endswith("." + d) for d in domains) if host else request.headers.get("origin", "").rstrip("/") in ORIGINS
        if not ok:
            raise HTTPException(403, "This website is not allowed to use this assistant.")
    return biz


@app.get("/public/businesses")
def public_businesses():
    out = []
    for b in q("SELECT * FROM businesses ORDER BY created"):
        if agent_of(b)["enabled"]:
            p = json.loads(b["profile"])
            out.append({"name": p["name"], "category": p.get("category", "Other"), "widget_id": b["widget_id"]})
    return out


@app.get("/widget/{wid}/config")
def widget_config(wid: str, request: Request):
    biz = widget_biz(wid, request)
    a, p = agent_of(biz), json.loads(biz["profile"])
    return {"name": p["name"], "enabled": a["enabled"], "currency": p.get("currency", "PKR"), "brand_color": a["brand_color"],
            "welcome": a["welcome"] or f"Hi! I'm the assistant for {p['name']}. How can I help?", "suggestions": a["suggestions"],
            "voice": bool(a["voice"] and API_KEY), "chat": bool(client)}


@app.get("/widget/{wid}/messages/{cid}")
def widget_messages(wid: str, cid: str, request: Request, after_id: int = 0):
    """Customer chat polls this to receive messages written by the business (owner or dashboard AI)."""
    limit(f"poll:{ip(request)}", 120, 60)
    biz = widget_biz(wid, request)
    known_conv(biz, cid)
    rows = q("SELECT id, role, content, created FROM messages WHERE conv=:c AND biz=:b AND role='business' AND id>:a ORDER BY id LIMIT 50",
             c=cid, b=biz["id"], a=max(0, after_id))
    return {"messages": rows}


@app.get("/widget.js")
def widget_js():
    js = """(function(){var s=document.currentScript,w=s.getAttribute("data-widget");if(!w)return;
var f=document.createElement("iframe");f.src="__F__/#/embed/"+encodeURIComponent(w)+"?host="+encodeURIComponent(location.hostname);
f.title="Chat assistant";f.allow="microphone";var t=f.style;t.position="fixed";t.border="0";t.zIndex="2147483647";t.background="transparent";t.colorScheme="normal";
function size(o){var m=innerWidth<500;t.width=o?(m?"100vw":"390px"):"76px";t.height=o?(m?"100vh":"640px"):"76px";t.right=o&&m?"0":"16px";t.bottom=o&&m?"0":"16px"}
size(false);addEventListener("message",function(e){if(e.source===f.contentWindow&&e.data&&e.data.bn)size(e.data.bn==="open")});document.body.appendChild(f)})();""".replace("__F__", FRONTEND_URL)
    return Response(js, media_type="application/javascript", headers={"Cache-Control": "public, max-age=300"})


# ---------------------------------------------------------------- customer agent: prompt + tools
def build_prompt(biz, conv=None, voice=False):
    p, a, b = json.loads(biz["profile"]), agent_of(biz), biz["id"]
    cur = p.get("currency") or "PKR"
    try:
        now = datetime.now(ZoneInfo(p.get("timezone") or "UTC"))
    except Exception:
        now = datetime.now(timezone.utc)
    items = "\n".join(f"- {i['name']} | {cur} {i['price']:g} | {i['category']} | {(i['description'] or '')[:80]} | {'untracked stock' if i['stock'] is None else 'stock ' + str(i['stock'])}"
                      for i in q("SELECT * FROM items WHERE biz=:b AND available=1 ORDER BY category,name LIMIT 100", b=b)) or "(no products or services added yet)"
    pend = one("SELECT number,total FROM orders WHERE conv=:c AND status=:s ORDER BY id DESC", c=conv, s=AWAIT) if conv else None
    tasks = ", ".join(k for k, v in a["tasks"].items() if v) or "answering questions only"
    return f"""You are the AI assistant of "{p['name']}" ({p.get('category', 'Other')}). Time: {now.strftime('%a %d %b %Y, %I:%M %p')} ({p.get('timezone')}).
Tone: {a['tone']}. Language: {a['language']} (customers may use English, Urdu or Roman Urdu; reply in their style). Be brief and natural.{' You are on a voice call: short sentences, never read long lists aloud.' if voice else ''}
Tasks: {tasks}. Fulfillment: {', '.join(a['fulfillment'])}. Delivery fee: {cur} {a['delivery_fee']:g}. Tax: {a['tax_percent']:g}%.

BUSINESS FACTS (only source of truth)
About: {p.get('description') or 'not provided'}
Hours: {p.get('hours') or 'not provided'} | Phone: {p.get('phone') or 'not provided'} | Address: {p.get('address') or 'not provided'} | Support: {p.get('support') or 'not provided'}
Owner instructions: {a['instructions'] or 'none'}
Knowledge base: {(biz['knowledge'] or 'none')[:4000]}
Products/services (name | price | category | description | stock):
{items}

RULES
- Product/service questions: call search_items first, answer only from results. Offer 2-3 options if asked for recommendations, then gently offer to order.
- Business info: answer only from BUSINESS FACTS. If missing, say so and offer request_human.
- Complaints, refunds, custom/bulk requests, or anything you can't answer: call request_human; say someone will follow up; promise no time or outcome.
- Off-topic: steer back politely. Greeting: greet and ask one question.
- Never invent prices, stock, discounts, policies, delivery times or completed actions. Ask one question at a time; never re-ask known details.
- Privacy: never give the owner's private contact details, internal notes, employee or dashboard info. Never use the business address as the customer's address. Ask for the customer's address only for Delivery.
- ORDER: collect name, phone, email, items and quantities, Pickup or Delivery, delivery address (if Delivery), special notes. Then call prepare_order and handle errors honestly. Summarize items, quantities, charges and total, and tell the customer to press the Confirm order button. It is not confirmed until they do. After they confirm, say a confirmation email will be sent to their email.
- Never claim an order is confirmed, paid or dispatched unless the system says so. Never take payment details.
- Order changes: prepare the full updated order for re-confirmation. Order status: ask for order number and the phone/email used, then call get_order_status; never reveal an order without them. Mention that status updates are emailed.
- Messages starting with "[Business team]" come from staff; follow them unless they break privacy or these rules.
- If a tool fails, explain briefly and offer the next safe step.
{f"- Order awaiting customer confirmation: {pend['number']} (total {cur} {pend['total']:g})." if pend else ''}"""


def tool_defs(a):
    t = [fn("search_items", "Search available products/services by keyword (empty query lists some).", {"query": S}, ["query"]),
         fn("get_order_status", "Look up an order's status. Needs the order number and the phone/email used when ordering.", {"number": S, "contact": S}, ["number", "contact"])]
    if a["tasks"].get("orders"):
        t.append(fn("prepare_order", "Validate an order against the catalog and create a summary awaiting the customer's button confirmation. Does NOT place the order.",
                    {"customer": S, "contact": S, "email": S, "fulfillment": S, "address": S, "notes": S,
                     "items": {"type": "array", "items": {"type": "object", "properties": {"name": S, "qty": {"type": "integer"}}, "required": ["name", "qty"]}}},
                    ["customer", "contact", "email", "fulfillment", "items"]))
    if a["tasks"].get("handoff"):
        t.append(fn("request_human", "Ask a human from the business to take over this conversation.", {"reason": S}, ["reason"]))
    return t


def _err(m):
    return {"ok": False, "error": m}


def t_search(biz, a, conv, args):
    k = f"%{str(args.get('query', ''))[:60].lower()}%"
    rows = q("SELECT name,description,category,price,stock FROM items WHERE biz=:b AND available=1 AND (LOWER(name) LIKE :k OR LOWER(category) LIKE :k OR LOWER(description) LIKE :k) ORDER BY name LIMIT 10", b=biz["id"], k=k)
    ev(biz["id"], "agent", "Product searched", str(args.get("query", ""))[:100])
    return {"ok": True, "matches": [{**{x: r[x] for x in ("name", "description", "category", "price")}, "in_stock": r["stock"] is None or r["stock"] > 0} for r in rows]}


def t_prepare(biz, a, conv, args):
    b = biz["id"]
    customer, contact = str(args.get("customer", "")).strip()[:100], str(args.get("contact", "")).strip()[:200]
    address, notes, ful = str(args.get("address", "")).strip()[:200], str(args.get("notes", "")).strip()[:300], str(args.get("fulfillment", "")).strip()
    email = str(args.get("email", "")).strip().lower()[:200]
    if not customer or not contact:
        return _err("Customer name and contact (phone or email) are required.")
    if not EMAIL_RE.match(email):
        return _err("A valid customer email is required so order updates can be emailed.")
    if ful not in a["fulfillment"]:
        return _err(f"Fulfillment must be one of: {', '.join(a['fulfillment'])}.")
    if ful == "Delivery" and not address:
        return _err("A delivery address is required.")
    raw = args.get("items") or []
    if not isinstance(raw, list) or not raw or len(raw) > 30:
        return _err("Add between 1 and 30 items.")
    agg = {}
    for it in raw:
        name, qty = str(it.get("name", "")).strip().lower(), int(it.get("qty", 0))
        rows = q("SELECT * FROM items WHERE biz=:b AND available=1 AND LOWER(name)=:n", b=b, n=name)
        if not rows and len(name) > 2:
            rows = q("SELECT * FROM items WHERE biz=:b AND available=1 AND LOWER(name) LIKE :n LIMIT 5", b=b, n=f"%{name}%")
        if len(rows) != 1:
            return _err(f"'{name}' is not available" if not rows else f"'{name}' is ambiguous: " + ", ".join(r["name"] for r in rows))
        if not 1 <= qty <= 100:
            return _err("Quantity must be between 1 and 100.")
        r = rows[0]
        agg.setdefault(r["id"], [r, 0])[1] += qty
    for r, qty in agg.values():
        if r["stock"] is not None and qty > r["stock"]:
            return _err(f"Only {r['stock']} of {r['name']} left.")
    subtotal = round(sum(r["price"] * qty for r, qty in agg.values()), 2)
    fee = round(float(a["delivery_fee"]), 2) if ful == "Delivery" else 0.0
    tax = round(subtotal * a["tax_percent"] / 100, 2)
    total = round(subtotal + fee + tax, 2)
    run("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE conv=:c AND status=:s)", c=conv, s=AWAIT)
    run("DELETE FROM orders WHERE conv=:c AND status=:s", c=conv, s=AWAIT)
    oid = run("INSERT INTO orders(biz,conv,customer,contact,email,address,fulfillment,notes,subtotal,delivery_fee,tax,total,status,payment_status,created) VALUES(:b,:c,:cu,:co,:em,:ad,:f,:n,:s,:fee,:t,:tot,:st,'Unpaid',:cr) RETURNING id",
              b=b, c=conv, cu=customer, co=contact, em=email, ad=address, f=ful, n=notes, s=subtotal, fee=fee, t=tax, tot=total, st=AWAIT, cr=time.time())
    number = f"ORD-{oid:05d}"
    run("UPDATE orders SET number=:n WHERE id=:i", n=number, i=oid)
    for r, qty in agg.values():
        run("INSERT INTO order_items(order_id,item_id,name,qty,price) VALUES(:o,:i,:n,:q,:p)", o=oid, i=r["id"], n=r["name"], q=qty, p=r["price"])
    ev(b, "agent", "Order summary generated", f"{number} - total {total:g}")
    return {"ok": True, "order_number": number, "status": AWAIT, "subtotal": subtotal, "delivery_fee": fee, "tax": tax, "total": total,
            "lines": [{"name": r["name"], "qty": qty, "unit_price": r["price"]} for r, qty in agg.values()],
            "note": "NOT placed yet. The customer must press the Confirm order button shown in the chat. No payment has been taken."}


def t_status(biz, a, conv, args):
    key = lambda s: re.sub(r"\D", "", str(s)) or str(s).strip().lower()
    o = one("SELECT * FROM orders WHERE biz=:b AND number=:n", b=biz["id"], n=norm_number(args.get("number")))
    if not o or key(o["contact"]) != key(args.get("contact", "")):
        return _err("No order found with that number and contact.")
    return {"ok": True, "number": o["number"], "status": o["status"], "payment_status": o["payment_status"], "total": o["total"]}


def t_human(biz, a, conv, args):
    run("UPDATE conversations SET handoff=1, handoff_note=:n WHERE id=:i AND biz=:b", n=str(args.get("reason", ""))[:300], i=conv, b=biz["id"])
    ev(biz["id"], "agent", "Human handoff requested", str(args.get("reason", ""))[:200])
    return {"ok": True, "note": "The business has been notified. Tell the customer a person will follow up; do not promise a time."}


TOOL_IMPL = {"search_items": t_search, "prepare_order": t_prepare, "get_order_status": t_status, "request_human": t_human}


def run_tool(biz, conv, name, args):
    if name not in {t["name"] for t in tool_defs(agent_of(biz))}:
        return _err("This action is not enabled for this business.")
    try:
        return TOOL_IMPL[name](biz, agent_of(biz), conv, args if isinstance(args, dict) else {})
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        ev(biz["id"], "error", f"Action failed: {name}", e)
        return _err("Invalid request.")
    except Exception as e:
        ev(biz["id"], "error", f"Action failed: {name}", e)
        return _err("The action could not be completed.")


def ensure_conv(biz, cid, channel="chat"):
    if cid and one("SELECT 1 AS x FROM conversations WHERE id=:i AND biz=:b", i=cid, b=biz["id"]):
        run("UPDATE conversations SET updated=:t WHERE id=:i", t=time.time(), i=cid)
        return cid
    cid = uuid.uuid4().hex
    run("INSERT INTO conversations(id,biz,channel,handoff,created,updated) VALUES(:i,:b,:c,0,:t,:t)", i=cid, b=biz["id"], c=channel, t=time.time())
    ev(biz["id"], "agent", "Conversation started", channel)
    return cid


def pending_of(conv):
    o = one("SELECT id FROM orders WHERE conv=:c AND status=:s ORDER BY id DESC", c=conv, s=AWAIT)
    return order_view(o["id"]) if o else None


def known_conv(biz, cid):
    if not one("SELECT 1 AS x FROM conversations WHERE id=:i AND biz=:b", i=cid, b=biz["id"]):
        raise HTTPException(404, "Conversation not found.")


# ---------------------------------------------------------------- customer endpoints
@app.post("/widget/{wid}/chat")
async def chat(wid: str, req: ChatReq, request: Request):
    limit(f"chat:{ip(request)}", 20, 60)
    biz = widget_biz(wid, request)
    if not agent_of(biz)["enabled"]:
        raise HTTPException(503, "This assistant is currently turned off.")
    if not client:
        raise HTTPException(503, "The assistant is not configured yet.")
    b, conv = biz["id"], ensure_conv(biz, req.conversation_id)
    add_msg(b, conv, "user", req.message)
    items = []
    for m in q("SELECT role,content FROM messages WHERE conv=:c ORDER BY id DESC LIMIT 20", c=conv)[::-1]:
        if m["role"] == "business":  # staff messages: the model only accepts user/assistant roles
            items.append({"role": "assistant", "content": "[Business team] " + m["content"]})
        else:
            items.append({"role": m["role"], "content": m["content"]})
    tools, t0, reply = tool_defs(agent_of(biz)), time.time(), "Sorry, I could not finish that. Please try again."
    try:
        for _ in range(5):
            resp = await client.responses.create(model=MODEL, instructions=build_prompt(biz, conv), input=items, tools=tools, max_output_tokens=900)
            calls = [o for o in resp.output if o.type == "function_call"]
            if not calls:
                reply = resp.output_text or reply
                break
            items += resp.output
            for c in calls:
                try:
                    args = json.loads(c.arguments)
                except ValueError:
                    args = {}
                items.append({"type": "function_call_output", "call_id": c.call_id, "output": json.dumps(run_tool(biz, conv, c.name, args))})
    except Exception as exc:
        print(f"OpenAI API error: {exc}")
        ev(b, "error", "AI provider error", exc)
        raise HTTPException(502, "The assistant is unavailable right now. Please try again.")
    add_msg(b, conv, "assistant", reply, int((time.time() - t0) * 1000))
    h = one("SELECT handoff FROM conversations WHERE id=:i", i=conv)["handoff"]
    return {"conversation_id": conv, "reply": reply, "pending_order": pending_of(conv), "handoff": h == 1}


@app.post("/widget/{wid}/orders/{number}/confirm")
def confirm_order(wid: str, number: str, body: ConvReq, request: Request):
    limit(f"confirm:{ip(request)}", 15, 60)
    biz = widget_biz(wid, request)
    b = biz["id"]
    o = one("SELECT * FROM orders WHERE biz=:b AND number=:n AND conv=:c", b=b, n=number, c=body.conversation_id or "")
    if not o:
        raise HTTPException(404, "Order not found.")
    if o["status"] == "Cancelled":
        raise HTTPException(409, "This order was cancelled.")
    if o["status"] != AWAIT:
        return {"order": order_view(o["id"]), "already_confirmed": True}  # idempotent repeat
    dup = False
    try:
        with engine.begin() as c:
            r = c.execute(text("UPDATE orders SET status='Confirmed', confirmed_at=:t WHERE id=:i AND status=:s"), {"t": time.time(), "i": o["id"], "s": AWAIT})
            if r.rowcount == 0:
                dup = True  # another request won the race
            else:
                for l in c.execute(text("SELECT * FROM order_items WHERE order_id=:i"), {"i": o["id"]}).mappings().all():
                    it = c.execute(text("SELECT price,available,stock FROM items WHERE id=:i AND biz=:b"), {"i": l["item_id"], "b": b}).mappings().first()
                    if not it or not it["available"] or abs(it["price"] - l["price"]) > 1e-6:
                        raise HTTPException(409, f"{l['name']} changed or is no longer available. Ask the assistant to prepare the order again.")
                    if it["stock"] is not None and not c.execute(text("UPDATE items SET stock=stock-:q WHERE id=:i AND stock>=:q"), {"q": l["qty"], "i": l["item_id"]}).rowcount:
                        raise HTTPException(409, f"Not enough stock for {l['name']}.")
                cu = c.execute(text("SELECT id FROM customers WHERE biz=:b AND contact=:c"), {"b": b, "c": o["contact"]}).first()
                if cu:
                    c.execute(text("UPDATE customers SET orders_count=orders_count+1, name=:n WHERE id=:i"), {"n": o["customer"], "i": cu[0]})
                else:
                    c.execute(text("INSERT INTO customers(biz,name,contact,orders_count,created) VALUES(:b,:n,:c,1,:t)"), {"b": b, "n": o["customer"], "c": o["contact"], "t": time.time()})
    except HTTPException as e:
        ev(b, "error", f"Order {number} could not be confirmed", e.detail)
        raise
    if not dup:
        ev(b, "agent", "Customer confirmation received", number)
        ev(b, "agent", "Order created", f"{number} - total {o['total']:g}")
        add_msg(b, body.conversation_id, "assistant", f"Order {number} was confirmed by the customer and sent to the business. Payment status: Unpaid.")
        email_confirmation(b, o)
        auto_process(b, o["id"])
    return {"order": order_view(o["id"]), "already_confirmed": dup}


@app.post("/widget/{wid}/tool")
def widget_tool(wid: str, body: ToolReq, request: Request):
    """Used by the voice agent (browser) to execute the same validated tools as text chat."""
    limit(f"tool:{ip(request)}", 40, 60)
    biz = widget_biz(wid, request)
    known_conv(biz, body.conversation_id)
    return {"result": run_tool(biz, body.conversation_id, body.name, body.args), "pending_order": pending_of(body.conversation_id)}


@app.post("/widget/{wid}/voice/log")
def voice_log(wid: str, body: LogReq, request: Request):
    limit(f"vlog:{ip(request)}", 60, 60)
    biz = widget_biz(wid, request)
    known_conv(biz, body.conversation_id)
    if body.role not in ("user", "assistant"):
        raise HTTPException(400, "Invalid role.")
    add_msg(biz["id"], body.conversation_id, body.role, body.content)
    return {"ok": True}


@app.post("/widget/{wid}/voice/session")
async def voice_session(wid: str, body: ConvReq, request: Request):
    limit(f"voice:{ip(request)}", 6, 60)
    biz = widget_biz(wid, request)
    a = agent_of(biz)
    if not a["enabled"] or not a["voice"] or not API_KEY:
        raise HTTPException(503, "Voice is not available.")
    conv = ensure_conv(biz, body.conversation_id, "voice")
    session = {"type": "realtime", "model": REALTIME_MODEL, "instructions": build_prompt(biz, conv, voice=True), "tools": tool_defs(a),
               "audio": {"input": {"transcription": {"model": "gpt-4o-mini-transcribe"}}, "output": {"voice": "marin"}}}
    try:
        async with httpx.AsyncClient(timeout=20) as h:
            r = await h.post("https://api.openai.com/v1/realtime/client_secrets", headers={"Authorization": f"Bearer {API_KEY}"}, json={"session": session})
        r.raise_for_status()
        secret = r.json()["value"]
    except Exception as exc:
        print(f"Realtime error: {exc}")
        ev(biz["id"], "error", "Voice session failed", exc)
        raise HTTPException(502, "Voice is unavailable right now. You can keep using text chat.")
    return {"client_secret": secret, "conversation_id": conv}