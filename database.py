"""
Enhanced database.py with visa requirements, pricing, and checklist templates.
This replaces the previous database.py
"""

import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "visa_system.db")


import libsql_experimental as libsql

def get_db():
    conn = libsql.connect(
        database=os.getenv("TURSO_DATABASE_URL"),
        auth_token=os.getenv("TURSO_AUTH_TOKEN")
    )
    conn.row_factory = sqlite3.Row
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

    # ── NEW: Client pricing / service charges ────────────────────────────────
    # Note: table/column names use "discount" for DB compatibility, but the
    # business logic in main.py treats these values as an ADDITIVE service
    # charge on top of the base price, not a price reduction.
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

    # ── Leads (pre-client inquiries) ───────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            email         TEXT,
            phone         TEXT,
            destination   TEXT,
            visa_type     TEXT,
            source        TEXT DEFAULT 'manual',   -- manual|website|whatsapp|referral|walk_in|call
            status        TEXT DEFAULT 'new',       -- new|contacted|qualified|quoted|won|lost
            assigned_to   INTEGER REFERENCES admin_users(id),
            notes         TEXT,
            converted_client_id INTEGER REFERENCES clients(id),
            created_by    TEXT,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Lead follow-ups ───────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS lead_followups (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id       INTEGER NOT NULL REFERENCES leads(id),
            due_at        DATETIME NOT NULL,
            note          TEXT,
            channel       TEXT DEFAULT 'call',     -- call|whatsapp|email|meeting
            status        TEXT DEFAULT 'pending',  -- pending|done|missed
            completed_at  DATETIME,
            created_by    TEXT,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Calendar events (visa appointments, travel dates, reminders) ───────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            event_type      TEXT DEFAULT 'other',    -- embassy_appointment|travel_date|followup|deadline|other
            start_at        DATETIME NOT NULL,
            end_at          DATETIME,
            all_day         INTEGER DEFAULT 0,
            client_id       INTEGER REFERENCES clients(id),
            app_id          TEXT,
            lead_id         INTEGER REFERENCES leads(id),
            location        TEXT,
            notes           TEXT,
            color           TEXT DEFAULT '#00a99c',
            reminder_minutes_before INTEGER,         -- e.g. 1440 = 1 day before, NULL = no reminder
            reminder_email  TEXT,                    -- who gets the email reminder
            reminder_sent   INTEGER DEFAULT 0,        -- 0=not sent, 1=email sent
            popup_seen_by   TEXT DEFAULT '[]',        -- JSON array of staff names who dismissed the popup
            created_by      TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Invoices ──────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no    TEXT UNIQUE NOT NULL,
            client_id     INTEGER NOT NULL REFERENCES clients(id),
            app_id        TEXT,
            line_items_json TEXT NOT NULL,        -- [{label, qty, unit_price, amount}]
            subtotal      DECIMAL(10,2) DEFAULT 0,
            discount      DECIMAL(10,2) DEFAULT 0,
            tax_percent   DECIMAL(5,2) DEFAULT 0,
            tax_amount    DECIMAL(10,2) DEFAULT 0,
            total         DECIMAL(10,2) DEFAULT 0,
            amount_paid   DECIMAL(10,2) DEFAULT 0,
            status        TEXT DEFAULT 'unpaid',   -- unpaid|partial|paid|overdue|cancelled
            due_date      TEXT,
            notes         TEXT,
            created_by    TEXT,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Invoice payments (partial payments allowed) ─────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS invoice_payments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id    INTEGER NOT NULL REFERENCES invoices(id),
            amount        DECIMAL(10,2) NOT NULL,
            method        TEXT DEFAULT 'cash',     -- cash|upi|card|bank_transfer|cheque|other
            reference     TEXT,
            paid_at       TEXT NOT NULL,
            notes         TEXT,
            recorded_by   TEXT,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Team chat (global, all staff see the same channel) ──────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS team_chat_messages (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id     INTEGER REFERENCES admin_users(id),
            sender_name   TEXT NOT NULL,
            sender_role   TEXT,
            message       TEXT NOT NULL,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Staff activity log (superadmin can view what each staff member does) ────
    c.execute("""
        CREATE TABLE IF NOT EXISTS staff_activity_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id      INTEGER REFERENCES admin_users(id),
            staff_name    TEXT NOT NULL,
            staff_role    TEXT,
            action        TEXT NOT NULL,   -- login|logout|create|update|delete|view|export|message
            detail        TEXT,            -- e.g. "Updated application VIS-2026-001"
            ip_address    TEXT,
            session_id    TEXT,
            created_at    DATETIME DEFAULT (datetime('now', '+5 hours', '+30 minutes'))
        )
    """)

    # ── Staff direct messages (superadmin ↔ any staff member) ────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS staff_direct_messages (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id       INTEGER NOT NULL REFERENCES admin_users(id),
            from_name     TEXT NOT NULL,
            to_id         INTEGER NOT NULL REFERENCES admin_users(id),
            to_name       TEXT NOT NULL,
            message       TEXT NOT NULL,
            is_ping       INTEGER DEFAULT 0,  -- 1 = urgent ping notification
            read_at       DATETIME,
            created_at    DATETIME DEFAULT (datetime('now', '+5 hours', '+30 minutes'))
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

    # ── Seed demo lead ──────────────────────────────────────────────────────
    c.execute("""
        INSERT OR IGNORE INTO leads (id, name, email, phone, destination, visa_type, source, status, created_by)
        VALUES (1, 'Priya Mehta', 'priya.mehta@email.com', '+919812345678', 'Singapore', 'tourist', 'website', 'new', 'system')
    """)
    c.execute("""
        INSERT OR IGNORE INTO lead_followups (lead_id, due_at, note, channel, status, created_by)
        VALUES (1, datetime('now', '+1 day'), 'Call to discuss Singapore package options', 'call', 'pending', 'system')
    """)

    # ── Seed demo calendar event ────────────────────────────────────────────
    c.execute("""
        INSERT OR IGNORE INTO calendar_events (id, title, event_type, start_at, client_id, app_id, notes, created_by)
        VALUES (1, 'UAE Embassy Appointment - Rahul Sharma', 'embassy_appointment', datetime('now', '+3 day'),
            (SELECT id FROM clients WHERE email='rahul.sharma@email.com'), 'VIS-2026-001',
            'Bring original passport and bank statements', 'system')
    """)

    # ── Seed demo invoice ────────────────────────────────────────────────────
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
    print(f"✓ Enhanced visa system DB initialised at {DB_PATH}")
