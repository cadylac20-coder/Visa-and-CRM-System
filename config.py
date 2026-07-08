import os
from dotenv import load_dotenv

load_dotenv()

# ── Authentication ────────────────────────────────────────────────────────────
SECRET_KEY  = os.getenv("SECRET_KEY")
TOKEN_HOURS = 12

# ── Turso Database ────────────────────────────────────────────────────────────
# Set these in Render → Environment
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN   = os.getenv("TURSO_AUTH_TOKEN")

# ── Superadmin (set in Render → Environment) ──────────────────────────────────
# These are ONLY used on first deploy to create the account via INSERT OR IGNORE.
# After that, changing the password in the UI is permanent — redeploy won't reset it.
SUPERADMIN_EMAIL = os.getenv("SUPERADMIN_EMAIL")
SUPERADMIN_NAME  = os.getenv("SUPERADMIN_NAME")
SUPERADMIN_PASS  = os.getenv("SUPERADMIN_PASS")

# ── Notifications ─────────────────────────────────────────────────────────────
GMAIL_ADDRESS      = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
WHATSAPP_TOKEN     = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID  = os.getenv("WHATSAPP_PHONE_ID", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE       = os.getenv("TWILIO_PHONE_NUMBER", "")

# ── App settings ──────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = ["*"]
MAX_FILE_MB     = 10
