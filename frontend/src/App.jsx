import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import logo from "./assets/logo.webp";

const API = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "bn_token";
// Maintenance band karne ke liye false kar dein
const MAINTENANCE_MODE = true;
const CURRENCY = (value, currency = "PKR") => {
  const n = Number(value || 0);
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(n);
  } catch {
    return `${currency} ${n.toFixed(2)}`;
  }
};
const getToken = () => localStorage.getItem(TOKEN_KEY) || "";
const authHeaders = () => ({ Authorization: `Bearer ${getToken()}` });

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.auth ? authHeaders() : {}),
      ...(options.headers || {}),
    },
  });
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data?.detail || data?.message || `Request failed (${response.status})`);
  return data;
}
const json = (body) => JSON.stringify(body);

const ORDER_STATUSES = [
  "Confirmed",
  "Accepted by Business",
  "Preparing or Processing",
  "Out for Delivery",
  "Completed",
  "Cancelled",
];

// Friendly labels for the actions the dashboard AI performs
const TOOL_LABELS = {
  search_orders: "Searched orders",
  update_order_status: "Updated order status",
  assign_order: "Assigned order",
  list_employees: "Checked team",
  list_conversations: "Listed conversations",
  read_customer_conversation: "Read conversation",
  reply_to_customer: "Replied to customer",
  resolve_handoff: "Resolved handoff",
  update_item: "Updated item",
  get_performance: "Checked performance",
  email_customer: "Emailed customer",
};

function readRoute() {
  const path = window.location.hash.replace(/^#\/?/, "");
  const parts = path.split("/").filter(Boolean);
  if (parts[0] === "store" && parts[1]) return { page: "store", widgetId: decodeURIComponent(parts[1]) };
  if (parts[0] === "embed" && parts[1]) return { page: "embed", widgetId: decodeURIComponent(parts[1]) };
  if (["login", "signup", "dashboard"].includes(parts[0])) return { page: parts[0] };
  return { page: "home" };
}
function navigate(path) {
  window.location.hash = `/${path}`;
}
function ErrorMessage({ children }) {
  return children ? <div className="bn-alert bn-alert-error" role="alert">{children}</div> : null;
}
function Notice({ children }) {
  return children ? <div className="bn-alert bn-alert-success" role="status">{children}</div> : null;
}
function Loading({ label = "Loading..." }) {
  return <div className="bn-loading"><span className="bn-spinner" />{label}</div>;
}

function Brand({ compact = false }) {
  return (
    <button
      className={`bn-brand ${compact ? "bn-brand-compact" : ""}`}
      onClick={() => navigate("/")}
      aria-label="Rides AI home"
    >
      <img src={logo} alt="" className="bn-brand-logo" />
      <span>Rides AI</span>
    </button>
  );
}

export default function App() {
  const [route, setRoute] = useState(readRoute);
  useEffect(() => {
    const update = () => setRoute(readRoute());
    window.addEventListener("hashchange", update);
    if (!window.location.hash) window.location.hash = "/";
    return () => window.removeEventListener("hashchange", update);
  }, []);

  if (route.page === "login") return <AuthPage mode="login" />;
  if (route.page === "signup") return <AuthPage mode="signup" />;
  if (route.page === "dashboard") return getToken()
    ? <Dashboard onLogout={() => { localStorage.removeItem(TOKEN_KEY); navigate("login"); }} />
    : <AuthPage mode="login" />;
  if (route.page === "store" || route.page === "embed") return <StorePage widgetId={route.widgetId} embedded={route.page === "embed"} />;
  return MAINTENANCE_MODE ? <MaintenancePage /> : <HomePage />;
}

function MaintenancePage() {
  return (
    <div className="bn-maint">
      <div className="bn-maint-brand"><Brand /></div>

      <div className="bn-maint-card">
        <svg className="bn-maint-art" viewBox="0 0 400 300" role="img" aria-label="Site under maintenance illustration">
          {/* background blob */}
          <ellipse cx="200" cy="265" rx="140" ry="16" fill="#a523a5" opacity=".12" />
          <circle cx="200" cy="140" r="115" fill="#a523a5" opacity=".08" />

          {/* browser window */}
          <rect x="70" y="60" width="260" height="170" rx="14" fill="#fff" stroke="#a523a5" strokeWidth="3" />
          <path d="M70 74a14 14 0 0 1 14-14h232a14 14 0 0 1 14 14v18H70z" fill="#a523a5" />
          <circle cx="90" cy="76" r="4" fill="#fff" />
          <circle cx="104" cy="76" r="4" fill="#fff" opacity=".7" />
          <circle cx="118" cy="76" r="4" fill="#fff" opacity=".4" />
          <rect x="92" y="190" width="120" height="8" rx="4" fill="#a523a5" opacity=".18" />
          <rect x="92" y="206" width="80" height="8" rx="4" fill="#a523a5" opacity=".18" />

          {/* big gear */}
          <g className="bn-maint-gear" style={{ transformOrigin: "200px 145px" }}>
            <path
              fill="#a523a5"
              d="M200 105l8 0 4 12 10 4 11-6 6 6-6 11 4 10 12 4v8l-12 4-4 10 6 11-6 6-11-6-10 4-4 12h-8l-4-12-10-4-11 6-6-6 6-11-4-10-12-4v-8l12-4 4-10-6-11 6-6 11 6 10-4z"
            />
            <circle cx="200" cy="145" r="16" fill="#fff" />
          </g>

          {/* small gear */}
          <g className="bn-maint-gear-rev" style={{ transformOrigin: "275px 105px" }}>
            <circle cx="275" cy="105" r="17" fill="none" stroke="#d946d9" strokeWidth="9" strokeDasharray="6 5" />
            <circle cx="275" cy="105" r="9" fill="#d946d9" />
          </g>

          {/* wrench */}
          <g transform="rotate(35 300 215)">
            <rect x="292" y="170" width="16" height="80" rx="8" fill="#6b1a6b" />
            <path d="M282 150a18 18 0 1 1 36 0v22h-12v-10h-12v10h-12z" fill="#6b1a6b" />
          </g>
        </svg>

        <span className="bn-eyebrow">WE’LL BE BACK SOON</span>
        <h1>This site is <em>under maintenance</em></h1>
        <p>
          We’re making some improvements to give you a better experience.
          Please check back in a little while. Thank you for your patience!
        </p>

      </div>

      <small className="bn-maint-foot">© {new Date().getFullYear()} Rides AI</small>
    </div>
  );
}

function HomePage() {
  return (
    <div className="bn-app">
      <header className="bn-header">
        <Brand />
        <nav className="bn-nav">
          <button className="bn-btn bn-btn-ghost" onClick={() => navigate("login")}>Log in</button>
          <button className="bn-btn bn-btn-primary" onClick={() => navigate("signup")}>Create business</button>
        </nav>
      </header>

      <main>
        <section className="bn-hero">
          <div className="bn-hero-copy">
            <span className="bn-eyebrow">YOUR PERSONAL BUSINESS ASSISTANT</span>
            <h1>One chat. Every business. <em>Things get done.</em></h1>
            <p>
              Discover businesses, ask questions, explore products and services,
              and place orders through one simple AI Agent.
            </p>
            <div className="bn-hero-actions">
              <button className="bn-btn bn-btn-primary bn-btn-lg" onClick={() => window.dispatchEvent(new Event("bn-open-customer-chat"))}>
                Chat/voice with AI Agent<span>↗</span>
              </button>
              <button className="bn-btn bn-btn-light bn-btn-lg" onClick={() => navigate("signup")}>
                Set up your business
              </button>
            </div>
            <div className="bn-hero-points">
              <span>✦ Discover available businesses</span>
              <span>✦ Review and confirm your orders</span>
            </div>
          </div>

          <div className="bn-hero-art" aria-hidden="true">
            <div className="bn-orbit bn-orbit-one" />
            <div className="bn-orbit bn-orbit-two" />
            <div className="bn-hero-bubble">
              <span className="bn-bubble-spark">✦</span>
              <span className="bn-bubble-face">☺</span>
              <span className="bn-bubble-dot" />
            </div>
            <div className="bn-float-card bn-float-top">
              <span className="bn-mini-icon">✦</span>
              <div><b>One Voice/Text Agent</b><small>Explore multiple businesses</small></div>
            </div>
            <div className="bn-float-card bn-float-bottom">
              <span className="bn-check">✓</span>
              <div><b>Order with confidence</b><small>Review before confirming</small></div>
            </div>
          </div>
        </section>

        <section className="bn-bottom-cta">
          <div>
            <span className="bn-eyebrow">FOR BUSINESS OWNERS</span>
            <h2>Give your customers their own Agent experience.</h2>
            <p>
              Add your business details, products, services and policies.
              Your AI assistant (Agent) can use that information to help your customers.
            </p>
          </div>
          <button className="bn-btn bn-btn-light bn-btn-lg" onClick={() => navigate("signup")}>
            Get started <span>↗</span>
          </button>
        </section>
      </main>

      <footer className="bn-footer">
        <Brand compact />
        <span>© {new Date().getFullYear()} Rides AI. Built for better conversations.</span>
        <button onClick={() => navigate("login")}>Business login</button>
      </footer>

      <CustomerAssistantWidget />
    </div>
  );
}

function CustomerAssistantWidget() {
  const [open, setOpen] = useState(false);
  const [businesses, setBusinesses] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);

  const loadBusinesses = useCallback(async () => {
    if (loaded || loading) return;
    setLoading(true);
    setError("");
    try {
      const data = await api("/public/businesses");
      setBusinesses(Array.isArray(data) ? data : data.businesses || []);
      setLoaded(true);
    } catch (e) {
      setError(e.message || "Could not load businesses.");
    } finally {
      setLoading(false);
    }
  }, [loaded, loading]);

  useEffect(() => {
    if (open && !selected) loadBusinesses();
  }, [open, selected, loadBusinesses]);

  useEffect(() => {
    const openChat = () => setOpen(true);
    window.addEventListener("bn-open-customer-chat", openChat);
    return () => window.removeEventListener("bn-open-customer-chat", openChat);
  }, []);

  const filteredBusinesses = useMemo(() => {
    const term = query.trim().toLowerCase();
    return businesses.filter((business) =>
      `${business.name || ""} ${business.category || ""}`.toLowerCase().includes(term)
    );
  }, [businesses, query]);

  function chooseBusiness(business) {
    if (!business?.widget_id) {
      setError("This business does not have a valid assistant ID.");
      return;
    }
    setError("");
    setSelected(business);
  }
  function backToBusinesses() { setSelected(null); setError(""); }
  function closeChat() { setOpen(false); }

  return (
    <div className="bn-customer-widget">
      {open && (
        <section className="bn-customer-panel" aria-label="Customer AI assistant">
          <header className="bn-customer-header">
            <span className="bn-customer-mark">✦</span>
            <div className="bn-customer-header-info">
              <b>{selected ? selected.name : "Rides AI AI"}</b>
              <small>{selected ? "Business-specific assistant" : "Discover businesses and start chatting"}</small>
            </div>
            {selected && (
              <button type="button" className="bn-customer-back" onClick={backToBusinesses} aria-label="Back to business list" title="Choose another business">←</button>
            )}
            <button type="button" className="bn-customer-close" onClick={closeChat} aria-label="Close chatbot">×</button>
          </header>

          {!selected ? (
            <div className="bn-customer-businesses">
              <div className="bn-customer-intro">
                <span className="bn-eyebrow">ONE CHAT, MANY BUSINESSES</span>
                <h3>Who would you like to talk to?</h3>
                <p>Select a business to chat/voice with its own AI assistant.</p>
              </div>
              <label className="bn-customer-search">
                <span>⌕</span>
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search businesses..." aria-label="Search businesses" />
              </label>
              <ErrorMessage>{error}</ErrorMessage>
              {loading ? (
                <Loading label="Finding businesses..." />
              ) : filteredBusinesses.length ? (
                <div className="bn-customer-business-list">
                  {filteredBusinesses.map((business) => (
                    <button type="button" className="bn-customer-business" key={business.widget_id} onClick={() => chooseBusiness(business)}>
                      <span className="bn-customer-business-avatar">{(business.name || "B").trim().charAt(0).toUpperCase()}</span>
                      <span className="bn-customer-business-details">
                        <b>{business.name || "Business"}</b>
                        <small>{business.category || "Independent business"}</small>
                      </span>
                      <span className="bn-customer-business-arrow">→</span>
                    </button>
                  ))}
                </div>
              ) : (
                !loading && (
                  <div className="bn-customer-empty">
                    <span>✦</span>
                    <b>{businesses.length ? "No matching businesses" : "No businesses available yet"}</b>
                    <p>
                      {businesses.length
                        ? "Try a different business name or category."
                        : "Please check back later, or create your own business workspace."}
                    </p>
                    {!businesses.length && (
                      <button className="bn-btn bn-btn-primary" onClick={() => { closeChat(); navigate("signup"); }}>Create a business</button>
                    )}
                  </div>
                )
              )}
              {!loaded && !loading && error && (
                <button className="bn-btn bn-btn-outline bn-btn-full" onClick={() => { setLoaded(false); loadBusinesses(); }}>Try again</button>
              )}
              <p className="bn-customer-footnote">Each business has its own assistant and business information.</p>
            </div>
          ) : (
            <div className="bn-customer-chat-body">
              <StorePage key={selected.widget_id} widgetId={selected.widget_id} embedded={false} floating onBackToBusinesses={backToBusinesses} />
            </div>
          )}
        </section>
      )}

      <button
        type="button"
        className={`bn-customer-launcher ${open ? "is-open" : ""}`}
        onClick={() => setOpen((value) => !value)}
        aria-label={open ? "Close customer chatbot" : "Open customer chatbot"}
        title="Chat with Rides AI AI"
      >
        {open ? "×" : <><i>Agent</i></>}
      </button>
    </div>
  );
}

function AuthPage({ mode }) {
  const signup = mode === "signup";
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const data = await api(signup ? "/auth/signup" : "/auth/login", {
        method: "POST",
        body: json({ name: name.trim() }),
      });
      localStorage.setItem(TOKEN_KEY, data.token);
      navigate("dashboard");
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return <div className="bn-auth-layout">
    <aside className="bn-auth-aside"><Brand /><div className="bn-auth-promo"><span className="bn-eyebrow">MEET YOUR BUSINESS ASSISTANT</span><h1>Less busywork.<br /><em>More possibility.</em></h1><p>One place to manage your business information and give customers a helpful AI experience.</p><div className="bn-auth-quote"><span>✦</span><p>“A better customer experience starts with a conversation.”</p></div></div><small className="bn-auth-foot">Rides AI · AI for every business</small></aside>
    <main className="bn-auth-main"><button className="bn-back-link" onClick={() => navigate("")}>← Back to home</button>
      <form className="bn-auth-form" onSubmit={submit}><span className="bn-eyebrow">{signup ? "START YOUR WORKSPACE" : "WELCOME BACK"}</span>
        <h2>{signup ? "Create your business" : "Log in to Rides AI"}</h2>
        <p>{signup ? "Enter your business name to launch your AI assistant. Currency PKR and timezone Asia/Karachi are set by default." : "Enter your business name to continue."}</p>
        <ErrorMessage>{error}</ErrorMessage>
        <label>Business name<input required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. The Little Studio" maxLength={100} autoFocus /></label>
        <button className="bn-btn bn-btn-primary bn-btn-full bn-btn-lg" disabled={busy || !name.trim()}>{busy ? "Please wait..." : signup ? "Create workspace →" : "Log in →"}</button>
        <p className="bn-auth-switch">{signup ? "Already have an account?" : "New to Rides AI?"} <button type="button" onClick={() => navigate(signup ? "login" : "signup")}>{signup ? "Log in" : "Create a business"}</button></p>
      </form>
    </main>
  </div>;
}

function StorePage({ widgetId, embedded, floating = false, onBackToBusinesses }) {
  const [config, setConfig] = useState(null);
  const [configError, setConfigError] = useState("");
  const [conversationId, setConversationId] = useState("");
  const [messages, setMessages] = useState([]);
  const [pending, setPending] = useState(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [callOpen, setCallOpen] = useState(false);
  const lastBusinessId = useRef(0);
  const endRef = useRef(null);

  useEffect(() => {
    api(`/widget/${encodeURIComponent(widgetId)}/config`)
      .then((data) => { setConfig(data); setMessages([{ role: "assistant", content: data.welcome }]); })
      .catch((e) => setConfigError(e.message));
  }, [widgetId]);

  useEffect(() => {
    if (!embedded) return;
    window.parent.postMessage({ bn: "open" }, "*");
    return () => window.parent.postMessage({ bn: "closed" }, "*");
  }, [embedded]);

  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [messages, busy, pending]);

  // Messages from the business (owner / dashboard AI)
  useEffect(() => {
    if (!conversationId) return;
    let stopped = false;
    const timer = window.setInterval(async () => {
      try {
        const data = await api(`/widget/${encodeURIComponent(widgetId)}/messages/${encodeURIComponent(conversationId)}?after_id=${lastBusinessId.current}`);
        if (stopped || !data.messages?.length) return;
        lastBusinessId.current = data.messages[data.messages.length - 1].id;
        setMessages((old) => [...old, ...data.messages.map((m) => ({ role: "assistant", content: m.content, business: true }))]);
      } catch { /* ignore */ }
    }, 5000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [conversationId, widgetId]);

  async function sendMessage(message) {
    const clean = message.trim();
    if (!clean || busy) return;
    setInput(""); setError(""); setBusy(true);
    setMessages((old) => [...old, { role: "user", content: clean }]);
    try {
      const data = await api(`/widget/${encodeURIComponent(widgetId)}/chat`, {
        method: "POST", body: json({ message: clean, conversation_id: conversationId || null }),
      });
      setConversationId(data.conversation_id);
      setPending(data.pending_order || null);
      setMessages((old) => [...old, { role: "assistant", content: data.reply || "Sorry, I couldn't generate a reply." }]);
    } catch (e) { setError(e.message || "Could not send your message."); }
    finally { setBusy(false); }
  }

  async function confirmOrder() {
    if (!pending || !conversationId || busy) return;
    const number = pending.number;
    setBusy(true); setError("");
    try {
      await api(`/widget/${encodeURIComponent(widgetId)}/orders/${encodeURIComponent(number)}/confirm`, {
        method: "POST", body: json({ conversation_id: conversationId }),
      });
      setPending(null);
      setMessages((old) => [...old, { role: "assistant", content: `Order ${number} has been confirmed. It still needs to be accepted by the business. Payment status: Unpaid.` }]);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  const goBack = () => {
    if (onBackToBusinesses) onBackToBusinesses();
    else if (embedded) window.parent.postMessage({ bn: "closed" }, "*");
    else navigate("");
  };
  const cls = `bn-chat-page ${embedded ? "bn-embedded" : ""} ${floating ? "bn-chat-floating" : ""}`;

  if (configError) return <div className={cls}><ErrorMessage>{configError}</ErrorMessage><button className="bn-btn bn-btn-ghost" onClick={goBack}>Back</button></div>;
  if (!config) return <div className={cls}><Loading label="Connecting to assistant..." /></div>;

  return (
    <div className={cls} style={{ "--bn-brand": config.brand_color || "#a523a5" }}>
      <header className="bn-chat-header">
        <button type="button" className="bn-chat-back" onClick={goBack}>{onBackToBusinesses ? "←" : embedded ? "×" : "←"}</button>
        <div className="bn-chat-avatar">✦</div>
        <div className="bn-chat-title"><b>{config.name}</b><span><i /> AI assistant · Usually replies instantly</span></div>
        {config.voice && <button type="button" className="bn-call-start" onClick={() => setCallOpen(true)} title="Start a voice call" aria-label="Start voice call">📞</button>}
      </header>

      <div className="bn-chat-content"><div className="bn-chat-date">YOUR CONVERSATION</div>
        {messages.map((m, i) => <div key={i} className={`bn-message-row ${m.role === "user" ? "bn-message-user" : ""}`}>
          {m.role !== "user" && <span className="bn-message-avatar">✦</span>}
          <div className={`bn-message ${m.business ? "bn-message-business" : ""}`}>
            {m.business && <small className="bn-message-tag">Business team</small>}
            {m.voice && <small className="bn-message-tag">🎙 Voice call</small>}
            <p>{m.content}</p>
          </div>
        </div>)}
        {busy && <div className="bn-message-row"><span className="bn-message-avatar">✦</span><div className="bn-message bn-typing"><i /><i /><i /></div></div>}
        {pending && <div className="bn-order-card"><div className="bn-order-top"><span>ORDER SUMMARY</span><span className="bn-order-pending">Awaiting confirmation</span></div><h3>{pending.number}</h3>
          {(pending.lines || []).map((line, i) => <div className="bn-order-line" key={`${line.name}-${i}`}><span>{line.qty} × {line.name}</span><b>{CURRENCY(Number(line.unit_price ?? line.price) * Number(line.qty), config.currency)}</b></div>)}
          <div className="bn-order-totals"><div><span>Subtotal</span><span>{CURRENCY(pending.subtotal, config.currency)}</span></div><div><span>Delivery</span><span>{CURRENCY(pending.delivery_fee, config.currency)}</span></div><div><span>Tax</span><span>{CURRENCY(pending.tax, config.currency)}</span></div><div className="bn-order-total"><b>Total</b><b>{CURRENCY(pending.total, config.currency)}</b></div></div>
          <p className="bn-order-note">Review your details before confirming. No payment has been taken. Status updates will be emailed to you.</p>
          <button className="bn-btn bn-btn-primary bn-btn-full" onClick={confirmOrder} disabled={busy}>✓ Confirm order</button>
        </div>}
        <ErrorMessage>{error}</ErrorMessage>
        {!messages.some((m) => m.role === "user") && config.suggestions?.length > 0 && <div className="bn-chat-suggestions">{config.suggestions.map((s) => <button key={s} onClick={() => sendMessage(s)}>{s} ↗</button>)}</div>}
        <div ref={endRef} />
      </div>

      <form className="bn-chat-input-area" onSubmit={(e) => { e.preventDefault(); sendMessage(input); }}>
        {config.voice && <button type="button" className="bn-voice-btn" title="Talk to the assistant (voice call)" onClick={() => setCallOpen(true)} disabled={busy}>♫</button>}
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={`Message ${config.name}...`} aria-label="Message assistant" maxLength={2000} />
        <button className="bn-send-btn" type="submit" disabled={busy || !input.trim()} aria-label="Send message">↑</button>
      </form>
      <div className="bn-chat-disclaimer">AI can make mistakes. Confirm important details with the business.</div>

      {callOpen && <VoiceCallModal
        widgetId={widgetId} config={config} conversationId={conversationId}
        onConversation={setConversationId}
        onTranscript={(role, content) => setMessages((old) => [...old, { role, content, voice: true }])}
        onPending={setPending}
        onClose={() => setCallOpen(false)} />}
    </div>
  );
}

function VoiceCallModal({ widgetId, config, conversationId, onConversation, onTranscript, onPending, onClose }) {
  const [status, setStatus] = useState("connecting"); // connecting | live | error
  const [talking, setTalking] = useState(false);      // agent speaking
  const [muted, setMuted] = useState(false);
  const [secs, setSecs] = useState(0);
  const [err, setErr] = useState("");
  const res = useRef({ pc: null, stream: null, audio: null });
  const convRef = useRef(conversationId);
  const base = `/widget/${encodeURIComponent(widgetId)}`;

  useEffect(() => {
    let closed = false;
    async function logLine(role, text) {
      if (!text?.trim()) return;
      onTranscript(role, text.trim());
      try { await api(`${base}/voice/log`, { method: "POST", body: json({ conversation_id: convRef.current, role, content: text.trim().slice(0, 3000) }) }); } catch { /* ignore */ }
    }
    async function start() {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone is not available in this browser.");
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (closed) { stream.getTracks().forEach((t) => t.stop()); return; }
        res.current.stream = stream;
        const sess = await api(`${base}/voice/session`, { method: "POST", body: json({ conversation_id: convRef.current || null }) });
        convRef.current = sess.conversation_id; onConversation(sess.conversation_id);
        if (closed) return;

        const pc = new RTCPeerConnection();
        res.current.pc = pc;
        const audio = document.createElement("audio"); audio.autoplay = true; res.current.audio = audio;
        pc.ontrack = (e) => { audio.srcObject = e.streams[0]; };
        stream.getTracks().forEach((t) => pc.addTrack(t, stream));

        const dc = pc.createDataChannel("oai-events");
        dc.onopen = () => setStatus("live");
        dc.onmessage = async (msg) => {
          let e; try { e = JSON.parse(msg.data); } catch { return; }
          if (e.type === "response.created") setTalking(true);
          else if (e.type === "response.done") setTalking(false);
          else if (e.type === "conversation.item.input_audio_transcription.completed") logLine("user", e.transcript);
          else if (e.type === "response.output_audio_transcript.done") logLine("assistant", e.transcript);
          else if (e.type === "response.function_call_arguments.done") {
            let output;
            try {
              let args = {}; try { args = JSON.parse(e.arguments || "{}"); } catch { /* ignore */ }
              const r = await api(`${base}/tool`, { method: "POST", body: json({ conversation_id: convRef.current, name: e.name, args }) });
              onPending(r.pending_order || null);
              output = r.result;
            } catch (x) { output = { ok: false, error: x.message || "Action failed." }; }
            dc.send(JSON.stringify({ type: "conversation.item.create", item: { type: "function_call_output", call_id: e.call_id, output: JSON.stringify(output) } }));
            dc.send(JSON.stringify({ type: "response.create" }));
          }
        };

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        const r = await fetch("https://api.openai.com/v1/realtime/calls", {
          method: "POST", body: offer.sdp,
          headers: { Authorization: `Bearer ${sess.client_secret}`, "Content-Type": "application/sdp" },
        });
        if (!r.ok) throw new Error("Could not connect the voice call.");
        await pc.setRemoteDescription({ type: "answer", sdp: await r.text() });
      } catch (e) {
        if (closed) return;
        setErr(e.name === "NotAllowedError" ? "Please allow microphone access to start the call." : e.message || "Voice call failed.");
        setStatus("error");
      }
    }
    start();
    return () => {
      closed = true;
      res.current.pc?.close();
      res.current.stream?.getTracks().forEach((t) => t.stop());
      if (res.current.audio) res.current.audio.srcObject = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (status !== "live") return;
    const t = window.setInterval(() => setSecs((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, [status]);

  function toggleMute() {
    const next = !muted;
    res.current.stream?.getAudioTracks().forEach((t) => { t.enabled = !next; });
    setMuted(next);
  }
  const mmss = `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;
  const label = status === "connecting" ? "Connecting…" : status === "error" ? "Call failed" : talking ? "Speaking…" : muted ? "Muted" : "Listening…";

  return <div className="bn-call-overlay" role="dialog" aria-label="Voice call">
    <div className="bn-call-card">
      <div className={`bn-call-avatar ${talking ? "is-talking" : ""} ${status === "live" && !talking ? "is-listening" : ""}`}>✦</div>
      <h3>{config.name}</h3>
      <p className="bn-call-status">{label}</p>
      {status === "live" && <p className="bn-call-timer">{mmss}</p>}
      {err && <div className="bn-alert bn-alert-error">{err}</div>}
      <small className="bn-call-hint">Your conversation is saved in the chat after the call.</small>
      <div className="bn-call-actions">
        <button type="button" className={`bn-call-btn ${muted ? "is-on" : ""}`} onClick={toggleMute} disabled={status !== "live"} aria-label={muted ? "Unmute" : "Mute"}>{muted ? "🔇" : "🎤"}</button>
        <button type="button" className="bn-call-btn bn-call-end" onClick={onClose} aria-label="End call">✕</button>
      </div>
    </div>
  </div>;
}

function Dashboard({ onLogout }) {
  const [state, setState] = useState(null);
  const [section, setSection] = useState("Overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState(null);
  const [agent, setAgent] = useState(null);
  const [knowledge, setKnowledge] = useState("");
  const [itemForm, setItemForm] = useState({ name: "", description: "", category: "General", price: "", stock: "", image: "" });
  const [employeeForm, setEmployeeForm] = useState({ name: "", email: "", role: "Staff" });
  const [conversation, setConversation] = useState(null);

  const refresh = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    try {
      const data = await api("/me/state", { auth: true });
      setState(data); setProfile(data.profile); setAgent(data.agent); setKnowledge(data.knowledge || "");
      setError("");
    } catch (e) {
      setError(e.message);
      if (/log in|unauthorized/i.test(e.message)) { localStorage.removeItem(TOKEN_KEY); navigate("login"); }
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(true); }, [refresh]);
  useEffect(() => {
    const timer = window.setInterval(() => refresh(false), 12000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  async function action(fn, successMessage = "Changes saved.") {
    setSaving(true); setError(""); setNotice("");
    try { await fn(); await refresh(false); setNotice(successMessage); }
    catch (e) { setError(e.message); }
    finally { setSaving(false); }
  }

  if (loading && !state) return <div className="bn-dashboard-loading"><Brand /><Loading label="Loading your workspace..." /></div>;
  if (!state) return <div className="bn-dashboard-loading"><Brand /><ErrorMessage>{error || "Could not load workspace."}</ErrorMessage><button className="bn-btn bn-btn-primary" onClick={() => refresh(true)}>Try again</button></div>;

  const currency = state.profile?.currency || "PKR";
  const orders = state.orders || [];
  const employees = state.employees || [];
  const pendingOrders = orders.filter((o) => o.status === "Awaiting Customer Confirmation");
  const navGroups = [
    { title: "WORKSPACE", items: [["Overview", "◫"], ["Orders", "▤"], ["Employees", "♧"], ["Products & services", "◇"], ["Customers", "♙"], ["Conversations", "☷"]] },
    { title: "AI ASSISTANT", items: [["AI agent", "✦"], ["Knowledge base", "▧"]] },
    { title: "BUSINESS", items: [["Business profile", "⚙"]] },
  ];

  async function addItem(e) {
    e.preventDefault();
    await action(async () => {
      await api("/me/items", { method: "POST", auth: true, body: json({ ...itemForm, price: Number(itemForm.price), stock: itemForm.stock === "" ? null : Number(itemForm.stock), available: true }) });
      setItemForm({ name: "", description: "", category: "General", price: "", stock: "", image: "" });
    }, "Product or service added.");
  }
  async function addEmployee(e) {
    e.preventDefault();
    await action(async () => {
      await api("/me/employees", { method: "POST", auth: true, body: json(employeeForm) });
      setEmployeeForm({ name: "", email: "", role: "Staff" });
    }, "Team member added.");
  }
  // The backend sets the order to Completed and notifies the customer in chat and by email.
  async function markDelivered(order) {
    if (!window.confirm(`Confirm that ${order.number} has been delivered to ${order.customer}?`)) return;
    await action(
      () => api(`/me/orders/${order.id}/delivered`, { method: "PATCH", auth: true }),
      "Order delivered and marked as Completed."
    );
  }
  async function saveProfile(e) {
    e.preventDefault();
    await action(() => api("/me/profile", { method: "PUT", auth: true, body: json(profile) }), "Business profile updated.");
  }
  async function saveAgent(e) {
    e.preventDefault();
    await action(() => api("/me/agent", { method: "PUT", auth: true, body: json(agent) }), "AI agent settings updated.");
  }
  async function saveKnowledge(e) {
    e.preventDefault();
    await action(() => api("/me/knowledge", { method: "PUT", auth: true, body: json({ text: knowledge }) }), "Knowledge base saved.");
  }
  async function changeOrder(order, status) {
    await action(() => api(`/me/orders/${order.id}`, { method: "PATCH", auth: true, body: json({ status }) }), "Order status updated.");
  }
  async function assignOrder(order, employeeId) {
    await action(() => api(`/me/orders/${order.id}/assign`, { method: "PATCH", auth: true, body: json({ employee_id: employeeId ? Number(employeeId) : null }) }), "Order assignment updated.");
  }
  async function openConversation(c) {
    setError("");
    try { setConversation(await api(`/me/conversations/${encodeURIComponent(c.id)}`, { auth: true })); }
    catch (e) { setError(e.message); }
  }

  return <div className="bn-dashboard">
    <aside className="bn-sidebar"><Brand /><div className="bn-sidebar-business"><span className="bn-sidebar-logo">{(profile?.name || "B").charAt(0).toUpperCase()}</span><div><b>{profile?.name}</b><small>Business workspace</small></div><span>⌄</span></div>
      {navGroups.map((group) => <div className="bn-nav-group" key={group.title}><small>{group.title}</small>{group.items.map(([label, icon]) => <button key={label} className={section === label ? "active" : ""} onClick={() => { setSection(label); setConversation(null); setError(""); setNotice(""); }}><span>{icon}</span>{label}{label === "Orders" && pendingOrders.length > 0 && <i>{pendingOrders.length}</i>}</button>)}</div>)}
      <div className="bn-sidebar-bottom"><button onClick={onLogout}>⇥ Log out</button><div className="bn-sidebar-user"><span className="bn-user-avatar">{(profile?.owner || profile?.name || "B").charAt(0).toUpperCase()}</span><div><b>{profile?.owner || "Business owner"}</b><small>{profile?.email || "Workspace admin"}</small></div></div></div>
    </aside>

    <main className="bn-dashboard-main"><header className="bn-dash-header"><div><div className="bn-breadcrumb">Workspace <span>/</span> {section}</div><h1>{section}</h1></div><div className="bn-dash-actions"><span className="bn-status-pill"><i /> AI workspace</span></div></header>
      <div className="bn-dash-content"><ErrorMessage>{error}</ErrorMessage><Notice>{notice}</Notice>{saving && <div className="bn-saving">Saving your changes…</div>}

        {section === "Overview" && <Overview state={state} currency={currency} onSection={setSection} onOpenConversation={openConversation} />}

        {section === "Orders" && <OrdersSection orders={orders} employees={employees} currency={currency} onStatus={changeOrder} onAssign={assignOrder} />}

        {section === "Employees" && <section className="bn-panel"><div className="bn-panel-heading"><div><h2>Employees</h2><p>Add your team. The AI assistant can assign orders to them for you.</p></div></div>
          <form className="bn-inline-form" onSubmit={addEmployee}><label>Name<input required maxLength={100} value={employeeForm.name} onChange={(e) => setEmployeeForm({ ...employeeForm, name: e.target.value })} /></label><label>Email<input type="email" value={employeeForm.email} onChange={(e) => setEmployeeForm({ ...employeeForm, email: e.target.value })} /></label><label>Role<input maxLength={60} value={employeeForm.role} onChange={(e) => setEmployeeForm({ ...employeeForm, role: e.target.value })} /></label><button className="bn-btn bn-btn-primary" disabled={saving}>+ Add employee</button></form>
          {employees.length > 0 && <div className="bn-emp-tasks"><h3 className="bn-subheading">Employee tasks</h3>
            {employees.map((emp) => {
              const mine = orders.filter((o) => o.assigned_to === emp.id && !["Completed", "Cancelled"].includes(o.status));
              return <div className="bn-emp-task-card" key={emp.id}><div className="bn-emp-task-head"><span className="bn-emp-avatar">{emp.name.charAt(0).toUpperCase()}</span><b>{emp.name}</b><small>{mine.length} active</small></div>
                {mine.length === 0 && <p className="bn-emp-task-empty">No active orders.</p>}
                {mine.map((o) => <div className="bn-emp-task-row" key={o.id}><div><b>{o.number}</b><small>{o.customer} · {o.fulfillment}{o.address ? ` · ${o.address}` : ""}</small></div><StatusTag status={o.status} />
                  <button className="bn-btn bn-btn-primary" disabled={o.status !== "Out for Delivery" || saving} title={o.status !== "Out for Delivery" ? "Waiting for owner to set Out for Delivery" : ""} onClick={() => markDelivered(o)}>✓ Delivered</button></div>)}
              </div>;
            })}
          </div>}
        </section>}

        {section === "Products & services" && <section className="bn-panel"><div className="bn-panel-heading"><div><h2>Products & services</h2><p>Manage the accurate catalog your AI assistant uses.</p></div></div>
          <form className="bn-inline-form bn-item-form" onSubmit={addItem}><label>Name<input required maxLength={150} value={itemForm.name} onChange={(e) => setItemForm({ ...itemForm, name: e.target.value })} placeholder="Product or service name" /></label><label>Category<input maxLength={60} value={itemForm.category} onChange={(e) => setItemForm({ ...itemForm, category: e.target.value })} /></label><label>Price<input required type="number" min="0" step="0.01" value={itemForm.price} onChange={(e) => setItemForm({ ...itemForm, price: e.target.value })} /></label><label>Stock <span className="bn-optional">Blank = untracked</span><input type="number" min="0" step="1" value={itemForm.stock} onChange={(e) => setItemForm({ ...itemForm, stock: e.target.value })} /></label><label className="bn-field-wide">Description<input maxLength={500} value={itemForm.description} onChange={(e) => setItemForm({ ...itemForm, description: e.target.value })} /></label><button className="bn-btn bn-btn-primary" disabled={saving}>+ Add item</button></form>
          <div className="bn-table-wrap"><table className="bn-table"><thead><tr><th>ITEM</th><th>CATEGORY</th><th>PRICE</th><th>STOCK</th><th>AVAILABILITY</th><th /></tr></thead><tbody>{state.items.map((item) => <tr key={item.id}><td><b>{item.name}</b><small>{item.description}</small></td><td>{item.category}</td><td>{CURRENCY(item.price, currency)}</td><td>{item.stock == null ? "Untracked" : item.stock}</td><td><span className={`bn-tag ${item.available ? "bn-tag-green" : "bn-tag-grey"}`}>{item.available ? "Available" : "Unavailable"}</span></td><td><button className="bn-text-btn" onClick={() => action(() => api(`/me/items/${item.id}`, { method: "PATCH", auth: true, body: json({ available: !item.available }) }), "Availability updated.")}>{item.available ? "Disable" : "Enable"}</button><button className="bn-text-btn bn-danger-text" onClick={() => { if (window.confirm(`Delete ${item.name}?`)) action(() => api(`/me/items/${item.id}`, { method: "DELETE", auth: true }), "Item deleted."); }}>Delete</button></td></tr>)}</tbody></table>{!state.items.length && <div className="bn-empty-inline">No products or services yet. Add your first item above.</div>}</div>
        </section>}

        {section === "Customers" && <DataTable title="Customers" description="Customers who have confirmed orders." columns={["CUSTOMER", "CONTACT", "CONFIRMED ORDERS", "ADDED"]} rows={state.customers.map((x) => [x.name || "—", x.contact || "—", x.orders_count || 0, dateText(x.created)])} />}

        {section === "Conversations" && <div className="bn-two-column"><section className="bn-panel"><div className="bn-panel-heading"><div><h2>Conversations</h2><p>Recent customer conversations and handoffs.</p></div></div><div className="bn-conversation-list">{state.conversations.map((c) => <button key={c.id} className={`bn-conversation-item ${conversation?.id === c.id ? "active" : ""}`} onClick={() => openConversation(c)}><span className="bn-conv-avatar">{c.channel === "voice" ? "♫" : "✦"}</span><span className="bn-conv-main"><b>{c.channel === "voice" ? "Voice conversation" : "Customer conversation"}</b><small>{dateText(c.updated)} · {c.msgs || 0} messages</small></span>{c.handoff === 1 && <i className="bn-tag bn-tag-orange">Handoff</i>}</button>)}</div>{!state.conversations.length && <div className="bn-empty-inline">No conversations yet.</div>}</section>
          <section className="bn-panel bn-conversation-detail"><div className="bn-panel-heading"><div><h2>Conversation details</h2><p>{conversation ? `ID ${conversation.id}` : "Select a conversation to read its messages."}</p></div>{conversation?.handoff === 1 && <button className="bn-btn bn-btn-outline" onClick={() => action(() => api(`/me/conversations/${encodeURIComponent(conversation.id)}/resolve`, { method: "POST", auth: true }), "Handoff resolved.")}>Resolve handoff</button>}</div>{conversation?.messages?.map((m, i) => <div key={i} className={`bn-transcript ${m.role === "user" ? "user" : ""}`}><small>{m.role === "user" ? "CUSTOMER" : m.role === "business" ? "BUSINESS TEAM" : "AI ASSISTANT"}</small><p>{m.content}</p></div>)}</section></div>}

        {section === "AI agent" && agent && <form className="bn-settings-form" onSubmit={saveAgent}><section className="bn-panel"><div className="bn-panel-heading"><div><h2>AI agent</h2><p>Choose how your assistant talks and which actions it can perform.</p></div><label className="bn-toggle"><input type="checkbox" checked={agent.enabled} onChange={(e) => setAgent({ ...agent, enabled: e.target.checked })} /><span /><b>{agent.enabled ? "Enabled" : "Disabled"}</b></label></div>
          <div className="bn-form-grid"><label>Conversation tone<input value={agent.tone} maxLength={100} onChange={(e) => setAgent({ ...agent, tone: e.target.value })} /></label><label>Language<input value={agent.language} maxLength={60} onChange={(e) => setAgent({ ...agent, language: e.target.value })} /></label><label className="bn-field-wide">Welcome message<textarea rows={2} maxLength={300} value={agent.welcome} onChange={(e) => setAgent({ ...agent, welcome: e.target.value })} placeholder="Leave blank to use the default welcome." /></label><label className="bn-field-wide">Owner instructions<textarea rows={4} maxLength={2000} value={agent.instructions} onChange={(e) => setAgent({ ...agent, instructions: e.target.value })} placeholder="Policies, priorities, and guidance for your assistant." /></label></div>
          <h3 className="bn-subheading">Enabled actions</h3><div className="bn-checkbox-grid">{Object.entries({ orders: "Prepare customer orders", handoff: "Request human assistance", auto_process: "Auto-accept & assign new orders" }).map(([key, label]) => <label key={key} className="bn-checkbox-card"><input type="checkbox" checked={!!agent.tasks?.[key]} onChange={(e) => setAgent({ ...agent, tasks: { ...agent.tasks, [key]: e.target.checked } })} /><span><b>{label}</b><small>{key === "orders" ? "Prepare an order summary for customer confirmation." : key === "handoff" ? "Mark conversations that need a team member." : "As soon as a customer confirms, the AI accepts it and assigns the least busy employee."}</small></span></label>)}</div>
          <div className="bn-form-grid"><label>Delivery fee ({currency})<input type="number" min="0" step="0.01" value={agent.delivery_fee} onChange={(e) => setAgent({ ...agent, delivery_fee: Number(e.target.value) })} /></label><label>Tax (%)<input type="number" min="0" max="100" step="0.01" value={agent.tax_percent} onChange={(e) => setAgent({ ...agent, tax_percent: Number(e.target.value) })} /></label><label>Brand color<input type="color" value={agent.brand_color || "#a523a5"} onChange={(e) => setAgent({ ...agent, brand_color: e.target.value })} /></label><label className="bn-checkbox-line"><input type="checkbox" checked={!!agent.voice} onChange={(e) => setAgent({ ...agent, voice: e.target.checked })} /> Enable voice option</label>
            <label className="bn-field-wide">Fulfillment options <small className="bn-help">Choose all options you support.</small><div className="bn-chip-checks">{["Pickup", "Delivery", "Dine-in", "On-site", "Online"].map((f) => <label key={f}><input type="checkbox" checked={agent.fulfillment.includes(f)} onChange={(e) => setAgent({ ...agent, fulfillment: e.target.checked ? [...agent.fulfillment, f] : agent.fulfillment.filter((x) => x !== f) })} />{f}</label>)}</div></label>
            <label className="bn-field-wide">Suggested questions <small className="bn-help">One suggestion per line, up to 6.</small><textarea rows={4} value={(agent.suggestions || []).join("\n")} onChange={(e) => setAgent({ ...agent, suggestions: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 6) })} placeholder={"What do you offer?\nHow can I place an order?"} /></label>
            <label className="bn-field-wide">Allowed website domains <small className="bn-help">One domain per line. Leave empty to allow any embed origin.</small><textarea rows={3} value={(agent.domains || []).join("\n")} onChange={(e) => setAgent({ ...agent, domains: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 20) })} placeholder={"example.com\nshop.example.com"} /></label>
          </div><button className="bn-btn bn-btn-primary" disabled={saving}>Save AI settings</button></section></form>}

        {section === "Knowledge base" && <form className="bn-panel" onSubmit={saveKnowledge}><div className="bn-panel-heading"><div><h2>Knowledge base</h2><p>Add reliable business information for your assistant to use when answering customers.</p></div></div><label>Business facts<textarea className="bn-knowledge-editor" rows={16} maxLength={8000} value={knowledge} onChange={(e) => setKnowledge(e.target.value)} placeholder={"Returns policy:\nShipping details:\nFrequently asked questions:\nOther important information:"} /></label><div className="bn-form-footer"><span>{knowledge.length}/8000 characters</span><button className="bn-btn bn-btn-primary" disabled={saving}>Save knowledge base</button></div></form>}

        {section === "Business profile" && profile && <form className="bn-panel" onSubmit={saveProfile}><div className="bn-panel-heading"><div><h2>Business profile</h2><p>These details help your assistant answer customers accurately.</p></div></div><div className="bn-form-grid">
          {[["name", "Business name"], ["category", "Category"], ["owner", "Owner name"], ["email", "Business email"], ["website", "Website"], ["phone", "Phone"], ["address", "Address"], ["hours", "Business hours"], ["support", "Support contact"]].map(([key, label]) => <label key={key} className={["address", "hours", "support"].includes(key) ? "bn-field-wide" : ""}>{label}<input value={profile[key] || ""} maxLength={key === "name" ? 100 : 300} onChange={(e) => setProfile({ ...profile, [key]: e.target.value })} /></label>)}
          <label>Currency<input required maxLength={6} value={profile.currency || "PKR"} onChange={(e) => setProfile({ ...profile, currency: e.target.value.toUpperCase() })} /></label><label>Timezone<input required value={profile.timezone || "Asia/Karachi"} onChange={(e) => setProfile({ ...profile, timezone: e.target.value })} /></label><label className="bn-field-wide">Description<textarea rows={4} maxLength={1000} value={profile.description || ""} onChange={(e) => setProfile({ ...profile, description: e.target.value })} /></label>
        </div>
        <div className="bn-setting-row"><div><b>Widget ID</b><code>{state.widget_id}</code></div><button type="button" className="bn-btn bn-btn-outline" onClick={() => navigator.clipboard?.writeText(state.widget_id)}>Copy ID</button></div>
        <button className="bn-btn bn-btn-primary" disabled={saving}>Save business profile</button></form>}
      </div>
    </main>

    <DashboardAssistant businessName={profile?.name || "your business"} onActions={() => refresh(false)} />

    <footer className="bn-mobile-footer"><Brand compact /><button onClick={onLogout}>Log out</button></footer>
  </div>;
}

/* ------------------------------------------------------------------
   Business voice call (dashboard). Uses the owner's authenticated
   endpoints: POST /me/agent/voice/session and POST /me/agent/tool
------------------------------------------------------------------- */
function DashboardCallModal({ businessName, onClose, onActions, onTranscript }) {
  const [status, setStatus] = useState("connecting"); // connecting | live | error
  const [talking, setTalking] = useState(false);
  const [muted, setMuted] = useState(false);
  const [secs, setSecs] = useState(0);
  const [err, setErr] = useState("");
  const [chips, setChips] = useState([]);
  const res = useRef({ pc: null, stream: null, audio: null });

  useEffect(() => {
    let closed = false;
    async function start() {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone is not available in this browser.");
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (closed) { stream.getTracks().forEach((t) => t.stop()); return; }
        res.current.stream = stream;
        const sess = await api("/me/agent/voice/session", { method: "POST", auth: true, body: json({}) });
        if (closed) return;

        const pc = new RTCPeerConnection();
        res.current.pc = pc;
        const audio = document.createElement("audio"); audio.autoplay = true; res.current.audio = audio;
        pc.ontrack = (e) => { audio.srcObject = e.streams[0]; };
        stream.getTracks().forEach((t) => pc.addTrack(t, stream));

        const dc = pc.createDataChannel("oai-events");
        dc.onopen = () => setStatus("live");
        dc.onmessage = async (msg) => {
          let e; try { e = JSON.parse(msg.data); } catch { return; }
          if (e.type === "response.created") setTalking(true);
          else if (e.type === "response.done") setTalking(false);
          else if (e.type === "conversation.item.input_audio_transcription.completed" && e.transcript?.trim()) onTranscript("user", e.transcript.trim());
          else if (e.type === "response.output_audio_transcript.done" && e.transcript?.trim()) onTranscript("assistant", e.transcript.trim());
          else if (e.type === "response.function_call_arguments.done") {
            let output;
            try {
              let args = {}; try { args = JSON.parse(e.arguments || "{}"); } catch { /* ignore */ }
              const r = await api("/me/agent/tool", { method: "POST", auth: true, body: json({ name: e.name, args }) });
              output = r.result;
              setChips((old) => [...old.slice(-3), { tool: e.name, ok: r.result?.ok !== false }]);
              onActions?.();
            } catch (x) {
              output = { ok: false, error: x.message || "Action failed." };
              setChips((old) => [...old.slice(-3), { tool: e.name, ok: false }]);
            }
            dc.send(JSON.stringify({ type: "conversation.item.create", item: { type: "function_call_output", call_id: e.call_id, output: JSON.stringify(output) } }));
            dc.send(JSON.stringify({ type: "response.create" }));
          }
        };

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        const r = await fetch("https://api.openai.com/v1/realtime/calls", {
          method: "POST", body: offer.sdp,
          headers: { Authorization: `Bearer ${sess.client_secret}`, "Content-Type": "application/sdp" },
        });
        if (!r.ok) throw new Error("Could not connect the voice call.");
        await pc.setRemoteDescription({ type: "answer", sdp: await r.text() });
      } catch (e) {
        if (closed) return;
        setErr(e.name === "NotAllowedError" ? "Please allow microphone access to start the call." : e.message || "Voice call failed.");
        setStatus("error");
      }
    }
    start();
    return () => {
      closed = true;
      res.current.pc?.close();
      res.current.stream?.getTracks().forEach((t) => t.stop());
      if (res.current.audio) res.current.audio.srcObject = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (status !== "live") return;
    const t = window.setInterval(() => setSecs((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, [status]);

  function toggleMute() {
    const next = !muted;
    res.current.stream?.getAudioTracks().forEach((t) => { t.enabled = !next; });
    setMuted(next);
  }
  const mmss = `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;
  const label = status === "connecting" ? "Connecting…" : status === "error" ? "Call failed" : talking ? "Speaking…" : muted ? "Muted" : "Listening…";

  return <div className="bn-call-overlay" role="dialog" aria-label="Voice call">
    <div className="bn-call-card">
      <div className={`bn-call-avatar ${talking ? "is-talking" : ""} ${status === "live" && !talking ? "is-listening" : ""}`}>✦</div>
      <h3>Rides AI AI</h3>
      <p className="bn-call-status">{label}</p>
      {status === "live" && <p className="bn-call-timer">{mmss}</p>}
      {chips.length > 0 && <div className="bn-call-chips">{chips.map((c, i) => <span key={i} className={`bn-dash-ai-chip ${c.ok ? "is-ok" : "is-fail"}`}>{c.ok ? "✓" : "✕"} {TOOL_LABELS[c.tool] || c.tool}</span>)}</div>}
      {err && <div className="bn-alert bn-alert-error">{err}</div>}
      <small className="bn-call-hint">Ask anything about {businessName}. The conversation appears in the chat panel.</small>
      <div className="bn-call-actions">
        <button type="button" className={`bn-call-btn ${muted ? "is-on" : ""}`} onClick={toggleMute} disabled={status !== "live"} aria-label={muted ? "Unmute" : "Mute"}>{muted ? "🔇" : "🎤"}</button>
        <button type="button" className="bn-call-btn bn-call-end" onClick={onClose} aria-label="End call">✕</button>
      </div>
    </div>
  </div>;
}

function DashboardAssistant({ businessName, onActions }) {
  const [open, setOpen] = useState(false);
  const [callOpen, setCallOpen] = useState(false);
  const [messages, setMessages] = useState([
    { role: "assistant", content: `Hi! I'm your Rides AI AI assistant for ${businessName}. I can find orders, assign them to employees, update status, reply to or email customers, and tell you how your business and team are performing.` },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [listening, setListening] = useState(false);
  const [voiceReplies, setVoiceReplies] = useState(false);
  const [speechLanguage, setSpeechLanguage] = useState("en-US");
  const endRef = useRef(null);

  useEffect(() => () => {
    if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy, open]);

  function speak(text) {
    if (!voiceReplies || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = speechLanguage;
    utterance.rate = 1;
    window.speechSynthesis.speak(utterance);
  }

  async function sendMessage(raw = input) {
    const clean = raw.trim();
    if (!clean || busy) return;
    setInput("");
    setError("");
    const history = messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .slice(-12)
      .map(({ role, content }) => ({ role, content }));
    setMessages((old) => [...old, { role: "user", content: clean }]);
    setBusy(true);
    try {
      const data = await api("/me/agent/chat", { method: "POST", auth: true, body: json({ message: clean, history }) });
      const reply = data.reply || "I couldn't create a response. Please try again.";
      const actions = data.actions || [];
      setMessages((old) => [...old, { role: "assistant", content: reply, actions }]);
      speak(reply);
      // refresh the dashboard so status / assignee changes show up immediately
      if (actions.some((a) => ["update_order_status", "assign_order", "update_item", "resolve_handoff", "reply_to_customer", "email_customer"].includes(a.tool) && a.ok)) onActions?.();
    } catch (e) {
      setError(e.message || "The assistant could not connect.");
    } finally {
      setBusy(false);
    }
  }

  function startListening() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError("Voice input isn't supported in this browser. Try Chrome or type your message instead.");
      return;
    }
    setError("");
    const recognition = new SpeechRecognition();
    recognition.lang = speechLanguage;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => setListening(true);
    recognition.onend = () => setListening(false);
    recognition.onerror = (event) => {
      setListening(false);
      setError(event.error === "not-allowed" ? "Please allow microphone access to use voice input." : "I couldn't hear that clearly. Please try again or type your message.");
    };
    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript || "";
      if (transcript.trim()) setInput((old) => old ? `${old} ${transcript}` : transcript);
    };
    recognition.start();
  }

  return <>
    {open && <section className="bn-dash-ai-panel" aria-label="Rides AI AI assistant">
      <header className="bn-dash-ai-head">
        <span className="bn-dash-ai-mark">✦</span>
        <div className="bn-dash-ai-title"><b>Rides AI AI</b><small>Business assistant · Text & voice</small></div>
        <button type="button" className="bn-call-start" onClick={() => setCallOpen(true)} title="Start a voice call" aria-label="Start voice call">📞</button>
        <button type="button" className="bn-dash-ai-close" onClick={() => setOpen(false)} aria-label="Close AI assistant">×</button>
      </header>
      <div className="bn-dash-ai-tools">
        <label>Speech language
          <select value={speechLanguage} onChange={(e) => setSpeechLanguage(e.target.value)}>
            <option value="en-US">English</option>
            <option value="ur-PK">Urdu</option>
            <option value="en-GB">English (UK)</option>
          </select>
        </label>
        <label className="bn-dash-ai-voice-toggle"><input type="checkbox" checked={voiceReplies} onChange={(e) => setVoiceReplies(e.target.checked)} /> Read replies aloud</label>
      </div>
      <div className="bn-dash-ai-messages" aria-live="polite">
        {messages.map((m, i) => <div key={`${i}-${m.role}`} className={`bn-dash-ai-message ${m.role === "user" ? "is-user" : "is-assistant"}`}>
          <span>{m.role === "user" ? "YOU" : "Rides AI AI"}</span>
          <p>{m.content}</p>
          {m.actions?.length > 0 && <div className="bn-dash-ai-actions">{m.actions.map((a, k) => <span key={k} className={`bn-dash-ai-chip ${a.ok ? "is-ok" : "is-fail"}`} title={a.result?.error || ""}>{a.ok ? "✓" : "✕"} {TOOL_LABELS[a.tool] || a.tool || "Action"}</span>)}</div>}
          {m.role === "assistant" && <button type="button" className="bn-dash-ai-speak" onClick={() => { if ("speechSynthesis" in window) { window.speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(m.content); u.lang = speechLanguage; window.speechSynthesis.speak(u); } }} title="Read this reply aloud">🔊 Listen</button>}
        </div>)}
        {busy && <div className="bn-dash-ai-thinking"><i /><i /><i /><span>Thinking…</span></div>}
        <ErrorMessage>{error}</ErrorMessage>
        <div ref={endRef} />
      </div>
      <div className="bn-dash-ai-quick">
        {[
          "How is today's business performance?",
          "How many orders does each employee have?",
          "What needs my attention?",
          "Give me tips to improve my business.",
        ].map((t) => (
          <button key={t} type="button" disabled={busy} onClick={() => sendMessage(t)}>{t}</button>
        ))}
      </div>
      <form className="bn-dash-ai-composer" onSubmit={(e) => { e.preventDefault(); sendMessage(); }}>
        <button type="button" className={`bn-dash-ai-mic ${listening ? "is-listening" : ""}`} onClick={startListening} disabled={busy || listening} aria-label="Speak a message" title="Speak a message">{listening ? "●" : "🎙"}</button>
        <input value={input} onChange={(e) => setInput(e.target.value)} maxLength={2000} placeholder="Ask about orders or customers…" aria-label="Message Rides AI AI" />
        <button type="submit" disabled={busy || !input.trim()} aria-label="Send message">↑</button>
      </form>
      <p className="bn-dash-ai-footnote">
        Try: “Assign ORD-00001 to Ali.” (The order is automatically accepted once assigned.)
      </p>

      {callOpen && <DashboardCallModal
        businessName={businessName}
        onActions={onActions}
        onTranscript={(role, content) => setMessages((old) => [...old, { role, content }])}
        onClose={() => setCallOpen(false)} />}
    </section>}
    <button type="button" className={`bn-dash-ai-launcher ${open ? "is-open" : ""}`} onClick={() => setOpen((value) => !value)} aria-label={open ? "Close AI assistant" : "Open AI assistant"} title="Talk to your AI assistant">
      {open ? "×" : <><span>✦</span><i>AI</i></>}
    </button>
  </>;
}

function Overview({ state, currency, onSection, onOpenConversation }) {
  const orders = state.orders || [];
  const active = orders.filter((o) => !["Completed", "Cancelled", "Awaiting Customer Confirmation"].includes(o.status));
  const pending = orders.filter((o) => o.status === "Awaiting Customer Confirmation");
  const cards = [
    ["Total conversations", state.metrics?.conversations || 0, "Across your assistant", "☷"],
    ["Awaiting confirmation", pending.length, "Customers need to confirm", "◷"],
    ["Active orders", active.length, "In progress with your team", "▤"],
    ["Completed order value", CURRENCY(state.metrics?.completed_value || 0, currency), "Completed orders only", "↗"],
  ];
  return <>
    <section className="bn-welcome-banner"><div><span className="bn-eyebrow">YOUR BUSINESS AT A GLANCE</span><h2>Welcome back{state.profile?.owner ? `, ${state.profile.owner}` : ""}.</h2><p>Here’s what’s happening with {state.profile?.name || "your business"} today.</p><div className="bn-welcome-actions"><button className="bn-btn bn-btn-light" onClick={() => onSection("Orders")}>Manage orders ↗</button><button className="bn-btn bn-btn-glass" onClick={() => onSection("AI agent")}>Configure AI agent</button></div></div><div className="bn-welcome-decoration">✦</div></section>
    <div className="bn-stat-grid">{cards.map(([label, value, sub, icon]) => <article className="bn-stat-card" key={label}><div className="bn-stat-top"><span>{label}</span><i>{icon}</i></div><strong>{value}</strong><small>{sub}</small></article>)}</div>
    <div className="bn-overview-grid"><section className="bn-panel"><div className="bn-panel-heading"><div><h2>Recent orders</h2><p>Review customer requests and update their progress.</p></div><button className="bn-text-btn" onClick={() => onSection("Orders")}>View all →</button></div><div className="bn-table-wrap"><table className="bn-table"><thead><tr><th>ORDER</th><th>CUSTOMER</th><th>TOTAL</th><th>STATUS</th></tr></thead><tbody>{orders.slice(0, 6).map((o) => <tr key={o.id}><td><b>{o.number}</b><small>{dateText(o.created)}</small></td><td>{o.customer}<small>{o.contact}</small></td><td>{CURRENCY(o.total, currency)}</td><td><StatusTag status={o.status} /></td></tr>)}</tbody></table>{!orders.length && <div className="bn-empty-inline">Your orders will appear here.</div>}</div></section>
      <section className="bn-panel bn-quick-panel"><div className="bn-panel-heading"><div><h2>Quick setup</h2><p>Keep your assistant ready to help.</p></div></div><button className="bn-quick-link" onClick={() => onSection("Products & services")}><span>◇</span><div><b>Add products & services</b><small>Keep prices and availability up to date</small></div><i>→</i></button><button className="bn-quick-link" onClick={() => onSection("Employees")}><span>♧</span><div><b>Add your employees</b><small>Let the AI assign orders to your team</small></div><i>→</i></button><button className="bn-quick-link" onClick={() => onSection("Knowledge base")}><span>▧</span><div><b>Build your knowledge base</b><small>Give accurate answers to customers</small></div><i>→</i></button><button className="bn-quick-link" onClick={() => onSection("AI agent")}><span>✦</span><div><b>Configure your AI agent</b><small>Set tone, tasks and fulfillment</small></div><i>→</i></button><button className="bn-quick-link" onClick={() => onSection("Business profile")}><span>⚙</span><div><b>Complete business profile</b><small>Add hours, contact and location</small></div><i>→</i></button></section>
    </div>
    <section className="bn-panel"><div className="bn-panel-heading"><div><h2>Recent conversations</h2><p>See what customers have been discussing.</p></div><button className="bn-text-btn" onClick={() => onSection("Conversations")}>All conversations →</button></div><div className="bn-recent-conversations">{(state.conversations || []).slice(0, 4).map((c) => <button key={c.id} className="bn-recent-conv" onClick={() => { onSection("Conversations"); onOpenConversation(c); }}><span className="bn-conv-avatar">✦</span><span><b>{c.channel === "voice" ? "Voice conversation" : "Customer conversation"}</b><small>{dateText(c.updated)} · {c.msgs || 0} messages</small></span>{c.handoff === 1 && <span className="bn-tag bn-tag-orange">Needs human</span>}<i>→</i></button>)}</div>{!state.conversations?.length && <div className="bn-empty-inline">Customer conversations will appear here.</div>}</section>
  </>;
}

function OrdersSection({ orders, employees = [], currency, onStatus, onAssign }) {
  const [filter, setFilter] = useState("All");
  const filtered = filter === "All" ? orders : orders.filter((o) => o.status === filter);
  const nameOf = (id) => employees.find((e) => e.id === id)?.name;
  return <section className="bn-panel"><div className="bn-panel-heading"><div><h2>Order management</h2><p>Customer confirmation is required before a new order can be processed.</p></div></div>
    <div className="bn-filter-row"><button className={filter === "All" ? "active" : ""} onClick={() => setFilter("All")}>All orders <span>{orders.length}</span></button>{["Awaiting Customer Confirmation", ...ORDER_STATUSES].map((s) => <button key={s} className={filter === s ? "active" : ""} onClick={() => setFilter(s)}>{s} <span>{orders.filter((o) => o.status === s).length}</span></button>)}</div>
    <div className="bn-order-list">{filtered.map((o) => {
      const open = o.status !== "Awaiting Customer Confirmation" && !["Completed", "Cancelled"].includes(o.status);
      return <article className="bn-order-row" key={o.id}>
        <div className="bn-order-row-head"><div><b>{o.number}</b><small>{dateText(o.created)}</small></div><StatusTag status={o.status} /></div>
        <div className="bn-order-customer"><b>{o.customer}</b><span>{o.contact}</span>{o.email && <span>✉ {o.email}</span>}{o.fulfillment && <span>{o.fulfillment}</span>}{o.assigned_to && <span className="bn-assignee">Assigned: {nameOf(o.assigned_to) || "—"}</span>}</div>
        <div className="bn-order-items">{(o.lines || []).map((l, i) => <div key={i}><span>{l.qty} × {l.name}</span><span>{CURRENCY(Number(l.qty) * Number(l.price), currency)}</span></div>)}</div>
        {o.address && <p className="bn-order-address">Delivery address: {o.address}</p>}
        {o.notes && <p className="bn-order-address">Notes: {o.notes}</p>}
        <div className="bn-order-row-foot"><div><small>Order total</small><strong>{CURRENCY(o.total, currency)}</strong><span className="bn-payment-status">Payment: {o.payment_status || "Unpaid"}</span></div>
          {open && <div className="bn-order-controls">
            <label className="bn-status-select">Assigned to
              <select value={o.assigned_to || ""} onChange={(e) => onAssign(o, e.target.value)}>
                <option value="">Unassigned</option>
                {employees.map((emp) => <option key={emp.id} value={emp.id}>{emp.name} ({emp.role})</option>)}
              </select>
            </label>
            <label className="bn-status-select">Update status<select value={o.status} onChange={(e) => onStatus(o, e.target.value)}><option value={o.status}>{o.status}</option>{ORDER_STATUSES.filter((s) => s !== o.status).map((s) => <option key={s}>{s}</option>)}</select></label>
            {o.fulfillment === "Delivery" && o.assigned_to && ["Accepted by Business", "Preparing or Processing"].includes(o.status) &&
              <button type="button" className="bn-btn bn-btn-primary bn-deliver-btn" onClick={() => onStatus(o, "Out for Delivery")}>🚚 Send for delivery</button>}
          </div>}
        </div>
        {o.status === "Awaiting Customer Confirmation" && <p className="bn-inline-warning">Waiting for the customer to press Confirm order in chat. You cannot process it yet.</p>}
      </article>;
    })}</div>{!filtered.length && <div className="bn-empty-inline">No orders in this view.</div>}
    {!employees.length && orders.length > 0 && <p className="bn-inline-warning">Add employees in the Employees section to assign orders.</p>}
  </section>;
}

function StatusTag({ status }) {
  let cls = "bn-tag-grey";
  if (status === "Completed" || status === "Confirmed") cls = "bn-tag-green";
  else if (status === "Cancelled") cls = "bn-tag-red";
  else if (status === "Awaiting Customer Confirmation") cls = "bn-tag-orange";
  else cls = "bn-tag-purple";
  return <span className={`bn-tag ${cls}`}>{status}</span>;
}

function DataTable({ title, description, columns, rows }) {
  return <section className="bn-panel"><div className="bn-panel-heading"><div><h2>{title}</h2><p>{description}</p></div></div><div className="bn-table-wrap"><table className="bn-table"><thead><tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody></table>{!rows.length && <div className="bn-empty-inline">Nothing to show yet.</div>}</div></section>;
}

function dateText(value) {
  if (!value) return "—"; 
  const date = new Date(Number(value) * 1000);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}