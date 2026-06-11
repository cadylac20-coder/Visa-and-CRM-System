import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY      = os.getenv("SECRET_KEY",      "visa-mkov-secret-change-in-production")
DB_PATH         = os.getenv("DB_PATH",          "visa_system.db")
UPLOAD_DIR      = os.getenv("UPLOAD_DIR",       "uploads")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL",  "")
DEFAULT_ADMIN   = os.getenv("DEFAULT_ADMIN",    "admin@uniglobemkov.in")
DEFAULT_PASS    = os.getenv("DEFAULT_PASS",     "admin123")
ALLOWED_ORIGINS = ["*"]
TOKEN_HOURS     = 12
MAX_FILE_MB     = 10
