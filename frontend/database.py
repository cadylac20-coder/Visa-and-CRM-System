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
            password   TEXT NOT NULL,           -- bcrypt hash
            role       TEXT DEFAULT 'staff',    -- staff | superadmin
            active     INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Clients ───────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            email         TEXT UNIQUE NOT NULL,
            phone         TEXT,
            password      TEXT NOT NULL,         -- bcrypt hash
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Applications ──────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id         TEXT UNIQUE NOT NULL,   -- VIS-YYYY-NNN
            client_id      INTEGER NOT NULL REFERENCES clients(id),
            destination    TEXT NOT NULL,
            visa_type      TEXT NOT NULL,           -- tourist|business|student|transit
            travel_date    TEXT,
            duration_days  INTEGER,
            group_size     INTEGER DEFAULT 1,
            status         TEXT DEFAULT 'pending', -- pending|docs_received|review|submitted|approved|rejected
            progress       INTEGER DEFAULT 10,
            assigned_to    INTEGER REFERENCES admin_users(id),
            embassy_ref    TEXT,
            notes          TEXT,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Documents ─────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id       TEXT NOT NULL REFERENCES applications(app_id),
            doc_type     TEXT NOT NULL,   -- passport|photo|bank_statement|hotel|flight|insurance|invitation|other
            file_name    TEXT,
            file_path    TEXT,            -- local path or Google Drive ID
            status       TEXT DEFAULT 'missing', -- missing|uploaded|verified|rejected
            uploaded_at  DATETIME,
            verified_at  DATETIME,
            notes        TEXT
        )
    """)

    # ── Activity log ──────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id     TEXT NOT NULL,
            actor      TEXT NOT NULL,   -- 'admin:<name>' or 'client:<name>' or 'system'
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
            channel    TEXT DEFAULT 'portal', -- portal|whatsapp|email
            read       INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── n8n webhook log ───────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS webhook_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            event      TEXT NOT NULL,
            payload    TEXT,
            status     TEXT DEFAULT 'pending', -- pending|sent|failed
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Seed admin user ───────────────────────────────────────────────────────
    from passlib.hash import bcrypt as bc
    admin_hash = bc.hash("admin123")
    c.execute("""
        INSERT OR IGNORE INTO admin_users (email, name, password, role)
        VALUES (?, ?, ?, ?)
    """, ("admin@uniglobemkov.in", "Admin User", admin_hash, "superadmin"))

    # ── Seed demo client + application ───────────────────────────────────────
    client_hash = bc.hash("rahul2024")
    c.execute("""
        INSERT OR IGNORE INTO clients (name, email, phone, password)
        VALUES (?, ?, ?, ?)
    """, ("Rahul Sharma", "rahul.sharma@email.com", "+91 98765 43210", client_hash))

    c.execute("""
        INSERT OR IGNORE INTO applications
            (app_id, client_id, destination, visa_type, travel_date, status, progress)
        VALUES (?,
            (SELECT id FROM clients WHERE email='rahul.sharma@email.com'),
            'Dubai', 'tourist', '2026-07-15', 'submitted', 75)
    """, ("VIS-2026-001",))

    doc_types = ["passport", "photo", "bank_statement", "hotel_booking", "flight_ticket"]
    statuses  = ["verified", "verified", "verified", "verified", "missing"]
    for dt, st in zip(doc_types, statuses):
        c.execute("""
            INSERT OR IGNORE INTO documents (app_id, doc_type, status)
            VALUES (?, ?, ?)
        """, ("VIS-2026-001", dt, st))

    for log in [
        ("system", "Application created",      "New visa application submitted"),
        ("system", "Checklist sent",            "Document checklist sent via WhatsApp"),
        ("admin:Admin User", "Docs verified",   "All uploaded documents verified"),
        ("admin:Admin User", "Status updated",  "Application submitted to UAE Embassy"),
    ]:
        c.execute("""
            INSERT OR IGNORE INTO activity_log (app_id, actor, action, detail)
            VALUES (?, ?, ?, ?)
        """, ("VIS-2026-001", log[0], log[1], log[2]))

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
    print(f"✓ Visa system DB initialised at {DB_PATH}")
