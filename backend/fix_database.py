
import os
from pathlib import Path
from dotenv import load_dotenv
from django.core.mail import send_mail
from django.conf import settings

# Load environment variables from backend/.env
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM") or SMTP_USER

# Validate credentials
if not SMTP_USER or not SMTP_PASS:
    raise ValueError(
        "SMTP_USER or SMTP_PASS missing. Check your backend/.env file."
    )

# Configure Django email settings
settings.configure(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST=SMTP_HOST,
    EMAIL_PORT=SMTP_PORT,
    EMAIL_USE_TLS=True,
    EMAIL_HOST_USER=SMTP_USER,
    EMAIL_HOST_PASSWORD=SMTP_PASS,
    DEFAULT_FROM_EMAIL=SMTP_FROM,
)

try:
    result = send_mail(
        subject="Bubble Nest - Test Email",
        message="Your Django SMTP email configuration is working!",
        from_email=SMTP_FROM,
        recipient_list=[SMTP_USER],
        fail_silently=False,
    )

    if result == 1:
        print(f"Email sent successfully to {SMTP_USER}")
    else:
        print("Email was not sent.")

except Exception as exc:
    print(f"Email error: {type(exc).__name__}: {exc}")
