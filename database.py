"""
Enhanced database.py with visa requirements, pricing, checklist templates, and staff activity tracking.
"""

import sqlite3
import os
from datetime import datetime
import pytz

DB_PATH = os.getenv("DB_PATH", "visa_system.db")
IST = pytz.timezone('Asia/Kolkata')

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def now_ist() -> datetime:
    """Get current IST time."""
    return datetime.now(IST)

def now_ist_str(fmt: str = "%Y-%m-%dT%H:%M:%S IST") -> str:
    """Get current IST time as formatted string."""
    return now_ist().strftime(fmt)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ── Admin users with enhanced roles ──────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            email           TEXT UNIQUE NOT NULL,
            name            TEXT NOT NULL,
            password        TEXT NOT NULL,
            role            TEXT DEFAULT 'staff',  -- superadmin|sales_admin|visa_admin|sales|visa_staff|staff
            active          INTEGER DEFAULT 1,
            last_login      DATETIME,
            session_start   DATETIME,
            session_end     DATETIME,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
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
            file_url     TEXT,
            status       TEXT DEFAULT 'missing',
            uploaded_at  DATETIME,
            verified_at  DATETIME,
            notes        TEXT
        )
    """)

    # ── Visa requirements ──────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS visa_requirements (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            country_code        TEXT UNIQUE NOT NULL,
            country_name        TEXT NOT NULL,
            visa_types_json     TEXT,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Custom checklist templates ─────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS custom_checklists (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            country         TEXT NOT NULL,
            visa_type       TEXT NOT NULL,
            name            TEXT,
            description     TEXT,
            documents_json  TEXT NOT NULL,
            base_price      DECIMAL(10,2) DEFAULT 0,
            discount_percentage DECIMAL(5,2) DEFAULT 0,
            final_price     DECIMAL(10,2),
            is_default      INTEGER DEFAULT 0,
            created_by      INTEGER REFERENCES admin_users(id),
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Client pricing ────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS client_discounts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id       INTEGER NOT NULL REFERENCES clients(id),
            checklist_id    INTEGER REFERENCES custom_checklists(id),
            discount_type   TEXT,
            discount_value  DECIMAL(10,2),
            reason          TEXT,
            active          INTEGER DEFAULT 1,
            created_by      INTEGER REFERENCES admin_users(id),
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Activity log (permanent change tracking) ───────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id     TEXT,
            actor_id   INTEGER REFERENCES admin_users(id),
            actor_name TEXT NOT NULL,
            action     TEXT NOT NULL,
            detail     TEXT,
            changes    TEXT,  -- JSON with before/after values
            timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Staff activity tracking (new) ──────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS staff_activity (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id    INTEGER NOT NULL REFERENCES admin_users(id),
            staff_name  TEXT NOT NULL,
            action      TEXT NOT NULL,  -- login|logout|view|create|edit|delete|message
            detail      TEXT,
            ip_address  TEXT,
            session_duration_minutes INTEGER,
            timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Notifications ─────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id  INTEGER REFERENCES clients(id),
            app_id     TEXT,
            message    TEXT NOT NULL,
            channel    TEXT DEFAULT 'portal',
            read       INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Communication log (WhatsApp, SMS, Email) ───────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS communication_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id          TEXT,
            client_id       INTEGER REFERENCES clients(id),
            channel         TEXT NOT NULL,
            phone_number    TEXT,
            email_address   TEXT,
            message_type    TEXT,
            message_content TEXT,
            sent_status     TEXT DEFAULT 'pending',
            response        TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Team notes ─────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS team_notes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id     TEXT NOT NULL,
            author_id  INTEGER REFERENCES admin_users(id),
            author     TEXT NOT NULL,
            note       TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Webhook log ────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS webhook_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            event      TEXT NOT NULL,
            payload    TEXT,
            status     TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Leads (pre-client inquiries) ───────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            name                TEXT NOT NULL,
            email               TEXT,
            phone               TEXT,
            destination         TEXT,
            visa_type           TEXT,
            source              TEXT DEFAULT 'manual',
            status              TEXT DEFAULT 'new',
            assigned_to         INTEGER REFERENCES admin_users(id),
            notes               TEXT,
            converted_client_id INTEGER REFERENCES clients(id),
            created_by          TEXT,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Lead follow-ups ───────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS lead_followups (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id       INTEGER NOT NULL REFERENCES leads(id),
            due_at        DATETIME NOT NULL,
            note          TEXT,
            channel       TEXT DEFAULT 'call',
            status        TEXT DEFAULT 'pending',
            completed_at  DATETIME,
            created_by    TEXT,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Calendar events ───────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            title                   TEXT NOT NULL,
            event_type              TEXT DEFAULT 'other',
            start_at                DATETIME NOT NULL,
            end_at                  DATETIME,
            all_day                 INTEGER DEFAULT 0,
            client_id               INTEGER REFERENCES clients(id),
            app_id                  TEXT,
            lead_id                 INTEGER REFERENCES leads(id),
            location                TEXT,
            notes                   TEXT,
            color                   TEXT DEFAULT '#00a99c',
            reminder_minutes_before INTEGER,
            reminder_email          TEXT,
            reminder_sent           INTEGER DEFAULT 0,
            popup_seen_by           TEXT DEFAULT '[]',
            created_by              TEXT,
            created_at              DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Invoices ──────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no      TEXT UNIQUE NOT NULL,
            client_id       INTEGER NOT NULL REFERENCES clients(id),
            app_id          TEXT,
            line_items_json TEXT NOT NULL,
            subtotal        DECIMAL(10,2) DEFAULT 0,
            discount        DECIMAL(10,2) DEFAULT 0,
            tax_percent     DECIMAL(5,2) DEFAULT 0,
            tax_amount      DECIMAL(10,2) DEFAULT 0,
            total           DECIMAL(10,2) DEFAULT 0,
            amount_paid     DECIMAL(10,2) DEFAULT 0,
            status          TEXT DEFAULT 'unpaid',
            due_date        TEXT,
            notes           TEXT,
            created_by      TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Invoice payments ──────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS invoice_payments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id  INTEGER NOT NULL REFERENCES invoices(id),
            amount      DECIMAL(10,2) NOT NULL,
            method      TEXT DEFAULT 'cash',
            reference   TEXT,
            paid_at     TEXT NOT NULL,
            notes       TEXT,
            recorded_by TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Team chat messages (new) ───────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS team_chat_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id   INTEGER REFERENCES admin_users(id),
            sender_name TEXT NOT NULL,
            sender_role TEXT,
            recipient_id INTEGER REFERENCES admin_users(id),  -- NULL = broadcast to all
            message     TEXT NOT NULL,
            is_pinned   INTEGER DEFAULT 0,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Seed admin user ───────────────────────────────────────────────────────
    import bcrypt
    admin_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
    c.execute("""
        INSERT OR IGNORE INTO admin_users (email, name, password, role, last_login)
        VALUES (?, ?, ?, ?, ?)
    """, ("admin@uniglobemkov.in", "Admin User", admin_hash, "superadmin", now_ist_str("%Y-%m-%d %H:%M:%S")))

    # ── Seed demo client ───────────────────────────────────────────────────────
    client_hash = bcrypt.hashpw(b"rahul2024", bcrypt.gensalt()).decode()
    c.execute("""
        INSERT OR IGNORE INTO clients (name, email, phone, password)
        VALUES (?, ?, ?, ?)
    """, ("Rahul Sharma", "rahul.sharma@email.com", "+919876543210", client_hash))

    # ── Seed demo application ──────────────────────────────────────────────────
    c.execute("""
        INSERT OR IGNORE INTO applications
            (app_id, client_id, destination, visa_type, travel_date, status, progress)
        VALUES (?,
            (SELECT id FROM clients WHERE email='rahul.sharma@email.com'),
            'Dubai', 'tourist', '2026-07-15', 'submitted', 75)
    """, ("VIS-2026-001",))

    # ── Seed demo documents ────────────────────────────────────────────────────
    doc_types = ["passport", "photo", "bank_statement", "hotel_booking", "flight_ticket"]
    statuses  = ["verified", "verified", "verified", "verified", "missing"]
    for dt, st in zip(doc_types, statuses):
        c.execute("""
            INSERT OR IGNORE INTO documents (app_id, doc_type, status)
            VALUES (?, ?, ?)
        """, ("VIS-2026-001", dt, st))

    # ── Activity log entries (now with permanent tracking) ──────────────────────
    for log in [
        ("system", "Application created", "New visa application submitted"),
        ("system", "Checklist sent", "Document checklist sent via WhatsApp"),
        ("admin:Admin User", "Docs verified", "All uploaded documents verified"),
        ("admin:Admin User", "Status updated", "Application submitted to UAE Embassy"),
    ]:
        c.execute("""
            INSERT OR IGNORE INTO activity_log (app_id, actor_name, action, detail, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, ("VIS-2026-001", log[0], log[1], log[2], now_ist_str("%Y-%m-%d %H:%M:%S")))

    # ── Notification ───────────────────────────────────────────────────────────
    c.execute("""
        INSERT OR IGNORE INTO notifications (client_id, app_id, message, read)
        VALUES (
            (SELECT id FROM clients WHERE email='rahul.sharma@email.com'),
            'VIS-2026-001',
            'Your application has been submitted to the UAE Embassy. Expected decision in 5-7 working days.',
            0)
    """)

    # ── Seed demo lead ────────────────────────────────────────────────────────
    c.execute("""
        INSERT OR IGNORE INTO leads (id, name, email, phone, destination, visa_type, source, status, created_by)
        VALUES (1, 'Priya Mehta', 'priya.mehta@email.com', '+919812345678', 'Singapore', 'tourist', 'website', 'new', 'system')
    """)
    c.execute("""
        INSERT OR IGNORE INTO lead_followups (lead_id, due_at, note, channel, status, created_by)
        VALUES (1, datetime('now', '+1 day'), 'Call to discuss Singapore package options', 'call', 'pending', 'system')
    """)

    # ── Seed demo calendar event ───────────────────────────────────────────────
    c.execute("""
        INSERT OR IGNORE INTO calendar_events (id, title, event_type, start_at, client_id, app_id, notes, created_by)
        VALUES (1, 'UAE Embassy Appointment - Rahul Sharma', 'embassy_appointment', datetime('now', '+3 day'),
            (SELECT id FROM clients WHERE email='rahul.sharma@email.com'), 'VIS-2026-001',
            'Bring original passport and bank statements', 'system')
    """)

    # ── Seed demo invoice ──────────────────────────────────────────────────────
    c.execute("""
        INSERT OR IGNORE INTO invoices
            (id, invoice_no, client_id, app_id, line_items_json, subtotal, total, amount_paid, status, due_date, created_by)
        VALUES (1, 'INV-2026-001',
            (SELECT id FROM clients WHERE email='rahul.sharma@email.com'), 'VIS-2026-001',
            '[{"label":"UAE Tourist Visa - Service Fee","qty":1,"unit_price":5000,"amount":5000}]',
            5000, 5000, 2000, 'partial', date('now', '+10 day'), 'system')
    """)
    c.execute("""
        INSERT OR IGNORE INTO invoice_payments (id, invoice_id, amount, method, paid_at, recorded_by)
        VALUES (1, 1, 2000, 'upi', date('now', '-2 day'), 'system')
    """)

    conn.commit()
    conn.close()
    print(f"✓ Enhanced visa system DB initialized at {DB_PATH} with IST timezone")
