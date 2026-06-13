"""
Enhanced database.py with visa requirements, pricing, and checklist templates.
This replaces the previous database.py
"""

import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "visa_system.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ── Admin users ───────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT UNIQUE NOT NULL,
            name       TEXT NOT NULL,
            password   TEXT NOT NULL,
            role       TEXT DEFAULT 'staff',
            active     INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Clients ───────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL,
            email            TEXT UNIQUE NOT NULL,
            phone            TEXT,
            password         TEXT NOT NULL,
            passport_b64     TEXT,
            passport_filename TEXT,
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Applications ──────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id         TEXT UNIQUE NOT NULL,
            client_id      INTEGER NOT NULL REFERENCES clients(id),
            destination    TEXT NOT NULL,
            visa_type      TEXT NOT NULL,
            travel_date    TEXT,
            duration_days  INTEGER,
            group_size     INTEGER DEFAULT 1,
            status         TEXT DEFAULT 'pending',
            progress       INTEGER DEFAULT 10,
            assigned_to    INTEGER REFERENCES admin_users(id),
            embassy_ref    TEXT,
            notes          TEXT,
            checklist_id   INTEGER REFERENCES custom_checklists(id),
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Documents ─────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id       TEXT NOT NULL REFERENCES applications(app_id),
            doc_type     TEXT NOT NULL,
            file_name    TEXT,
            file_path    TEXT,
            file_url     TEXT,           -- for cloud storage
            status       TEXT DEFAULT 'missing',
            uploaded_at  DATETIME,
            verified_at  DATETIME,
            notes        TEXT
        )
    """)

    # ── NEW: Visa requirements (read-only, from visa_requirements.py) ────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS visa_requirements (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            country_code        TEXT UNIQUE NOT NULL,
            country_name        TEXT NOT NULL,
            visa_types_json     TEXT,       -- JSON with all visa types + docs
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── NEW: Custom checklist templates with pricing ────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS custom_checklists (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            country         TEXT NOT NULL,
            visa_type       TEXT NOT NULL,
            name            TEXT,                  -- "USA Tourist Standard"
            description     TEXT,
            documents_json  TEXT NOT NULL,        -- JSON array of docs
            base_price      DECIMAL(10,2) DEFAULT 0,
            discount_percentage DECIMAL(5,2) DEFAULT 0,
            final_price     DECIMAL(10,2),
            is_default      INTEGER DEFAULT 0,    -- use default checklist
            created_by      INTEGER REFERENCES admin_users(id),
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── NEW: Client pricing/discounts ──────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS client_discounts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id       INTEGER NOT NULL REFERENCES clients(id),
            checklist_id    INTEGER REFERENCES custom_checklists(id),
            discount_type   TEXT,           -- 'percentage' | 'fixed'
            discount_value  DECIMAL(10,2),
            reason          TEXT,           -- "Group booking" | "Referral"
            active          INTEGER DEFAULT 1,
            created_by      INTEGER REFERENCES admin_users(id),
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Activity log ──────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id     TEXT NOT NULL,
            actor      TEXT NOT NULL,
            action     TEXT NOT NULL,
            detail     TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Notifications ─────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id  INTEGER NOT NULL REFERENCES clients(id),
            app_id     TEXT,
            message    TEXT NOT NULL,
            channel    TEXT DEFAULT 'portal',  -- portal | whatsapp | sms | email
            read       INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── NEW: Communication log (WhatsApp, SMS, Email) ──────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS communication_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id       TEXT,
            client_id    INTEGER REFERENCES clients(id),
            channel      TEXT NOT NULL,     -- whatsapp | sms | email
            phone_number TEXT,
            email_address TEXT,
            message_type TEXT,              -- checklist | status_update | reminder
            message_content TEXT,
            sent_status  TEXT DEFAULT 'pending',  -- pending | sent | failed
            response     TEXT,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Webhook log ───────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS team_notes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id     TEXT NOT NULL,
            author     TEXT NOT NULL,
            note       TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS webhook_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            event      TEXT NOT NULL,
            payload    TEXT,
            status     TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Seed admin user ───────────────────────────────────────────────────────
    import bcrypt
    admin_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
    c.execute("""
        INSERT OR IGNORE INTO admin_users (email, name, password, role)
        VALUES (?, ?, ?, ?)
    """, ("admin@uniglobemkov.in", "Admin User", admin_hash, "superadmin"))

    # ── Seed demo client ───────────────────────────────────────────────────
    client_hash = bcrypt.hashpw(b"rahul2024", bcrypt.gensalt()).decode()
    c.execute("""
        INSERT OR IGNORE INTO clients (name, email, phone, password)
        VALUES (?, ?, ?, ?)
    """, ("Rahul Sharma", "rahul.sharma@email.com", "+919876543210", client_hash))

    # ── Seed demo application ──────────────────────────────────────────────
    c.execute("""
        INSERT OR IGNORE INTO applications
            (app_id, client_id, destination, visa_type, travel_date, status, progress)
        VALUES (?,
            (SELECT id FROM clients WHERE email='rahul.sharma@email.com'),
            'Dubai', 'tourist', '2026-07-15', 'submitted', 75)
    """, ("VIS-2026-001",))

    # ── Seed demo documents ────────────────────────────────────────────────
    doc_types = ["passport", "photo", "bank_statement", "hotel_booking", "flight_ticket"]
    statuses  = ["verified", "verified", "verified", "verified", "missing"]
    for dt, st in zip(doc_types, statuses):
        c.execute("""
            INSERT OR IGNORE INTO documents (app_id, doc_type, status)
            VALUES (?, ?, ?)
        """, ("VIS-2026-001", dt, st))

    # ── Activity log entries ───────────────────────────────────────────────
    for log in [
        ("system", "Application created", "New visa application submitted"),
        ("system", "Checklist sent", "Document checklist sent via WhatsApp"),
        ("admin:Admin User", "Docs verified", "All uploaded documents verified"),
        ("admin:Admin User", "Status updated", "Application submitted to UAE Embassy"),
    ]:
        c.execute("""
            INSERT OR IGNORE INTO activity_log (app_id, actor, action, detail)
            VALUES (?, ?, ?, ?)
        """, ("VIS-2026-001", log[0], log[1], log[2]))

    # ── Notification ────────────────────────────────────────────────────────
    c.execute("""
        INSERT OR IGNORE INTO notifications (client_id, app_id, message, read)
        VALUES (
            (SELECT id FROM clients WHERE email='rahul.sharma@email.com'),
            'VIS-2026-001',
            'Your application has been submitted to the UAE Embassy. Expected decision in 5-7 working days.',
            0)
    """)

    conn.commit()
    conn.close()
    print(f"✓ Enhanced visa system DB initialised at {DB_PATH}")
