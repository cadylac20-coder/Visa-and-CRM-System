"""
database.py — Visa System with Turso cloud database
Uses 'libsql' package (pip install libsql) — the official 2025 replacement
for libsql-experimental. Same API, new name.

Superadmin credentials set via Render environment variables:
  SUPERADMIN_EMAIL  (default: admin@uniglobemkov.in)
  SUPERADMIN_PASS   (default: MkovAdmin@2026)
  SUPERADMIN_NAME   (default: Admin)

INSERT OR IGNORE ensures the superadmin is created ONCE on first deploy.
Password changes made through the UI survive all future redeploys.
"""

import sqlite3
import os
import libsql as turso
from dotenv import load_dotenv

load_dotenv()


def get_db():
    url   = os.getenv("TURSO_DATABASE_URL", "").strip()
    token = os.getenv("TURSO_AUTH_TOKEN", "").strip()

    if not url or not token:
        raise RuntimeError(
            "TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must be set in Render "
            "Environment settings. Go to your service -> Environment to add them."
        )

    conn = turso.connect(database=url, auth_token=token)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
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
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT NOT NULL,
            email             TEXT UNIQUE NOT NULL,
            phone             TEXT,
            password          TEXT NOT NULL,
            passport_b64      TEXT,
            passport_filename TEXT,
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
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
            checklist_id   INTEGER,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Documents (per-application) ───────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id      TEXT NOT NULL REFERENCES applications(app_id),
            doc_type    TEXT NOT NULL,
            file_name   TEXT,
            file_path   TEXT,
            file_url    TEXT,
            status      TEXT DEFAULT 'missing',
            uploaded_at DATETIME,
            verified_at DATETIME,
            notes       TEXT
        )
    """)

    # ── Visa requirements ─────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS visa_requirements (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            country_code    TEXT UNIQUE NOT NULL,
            country_name    TEXT NOT NULL,
            visa_types_json TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Custom checklists ─────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS custom_checklists (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            country             TEXT NOT NULL,
            visa_type           TEXT NOT NULL,
            name                TEXT,
            description         TEXT,
            documents_json      TEXT NOT NULL,
            base_price          REAL DEFAULT 0,
            discount_percentage REAL DEFAULT 0,
            final_price         REAL,
            is_default          INTEGER DEFAULT 0,
            created_by          TEXT,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Client service charges ────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS client_discounts (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id      INTEGER NOT NULL REFERENCES clients(id),
            checklist_id   INTEGER,
            discount_type  TEXT,
            discount_value REAL,
            reason         TEXT,
            active         INTEGER DEFAULT 1,
            created_by     TEXT,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Activity log (per application) ───────────────────────────────────────
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

    # ── Client notifications ──────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id  INTEGER NOT NULL REFERENCES clients(id),
            app_id     TEXT,
            message    TEXT NOT NULL,
            channel    TEXT DEFAULT 'portal',
            read       INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Outbound communication log ────────────────────────────────────────────
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

    # ── Internal team notes ───────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS team_notes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id     TEXT NOT NULL,
            author     TEXT NOT NULL,
            note       TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Webhook / API log ─────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS webhook_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            event      TEXT NOT NULL,
            payload    TEXT,
            status     TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Leads ─────────────────────────────────────────────────────────────────
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
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id      INTEGER NOT NULL REFERENCES leads(id),
            due_at       DATETIME NOT NULL,
            note         TEXT,
            channel      TEXT DEFAULT 'call',
            status       TEXT DEFAULT 'pending',
            completed_at DATETIME,
            created_by   TEXT,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
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
            subtotal        REAL DEFAULT 0,
            discount        REAL DEFAULT 0,
            tax_percent     REAL DEFAULT 0,
            tax_amount      REAL DEFAULT 0,
            total           REAL DEFAULT 0,
            amount_paid     REAL DEFAULT 0,
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
            amount      REAL NOT NULL,
            method      TEXT DEFAULT 'cash',
            reference   TEXT,
            paid_at     TEXT NOT NULL,
            notes       TEXT,
            recorded_by TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Hotel / accommodation CRM ─────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS hotel_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id       INTEGER NOT NULL REFERENCES clients(id),
            app_id          TEXT,
            hotel_name      TEXT NOT NULL,
            city            TEXT NOT NULL,
            country         TEXT NOT NULL,
            check_in        TEXT NOT NULL,
            check_out       TEXT NOT NULL,
            booking_ref     TEXT,
            booking_status  TEXT DEFAULT 'confirmed',
            room_type       TEXT,
            price_per_night REAL,
            total_price     REAL,
            currency        TEXT DEFAULT 'INR',
            notes           TEXT,
            is_future       INTEGER DEFAULT 0,
            created_by      TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Team chat ─────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS team_chat_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id   INTEGER REFERENCES admin_users(id),
            sender_name TEXT NOT NULL,
            sender_role TEXT,
            message     TEXT NOT NULL,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Staff activity log ────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS staff_activity_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id   INTEGER REFERENCES admin_users(id),
            staff_name TEXT NOT NULL,
            staff_role TEXT,
            action     TEXT NOT NULL,
            detail     TEXT,
            session_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Staff direct messages ─────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS staff_direct_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id    INTEGER NOT NULL REFERENCES admin_users(id),
            from_name  TEXT NOT NULL,
            to_id      INTEGER NOT NULL REFERENCES admin_users(id),
            to_name    TEXT NOT NULL,
            message    TEXT NOT NULL,
            is_ping    INTEGER DEFAULT 0,
            read_at    DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Document vault (client-level persistent storage) ──────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS document_vault (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id      INTEGER NOT NULL REFERENCES clients(id),
            doc_type       TEXT NOT NULL,
            file_name      TEXT,
            file_b64       TEXT,
            file_mime      TEXT DEFAULT 'application/octet-stream',
            status         TEXT DEFAULT 'uploaded',
            extracted_data TEXT,
            uploaded_by    TEXT,
            uploaded_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            verified_at    DATETIME,
            notes          TEXT
        )
    """)

    # ── Letter templates ──────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS letter_templates (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            template_type TEXT NOT NULL,
            country       TEXT,
            visa_type     TEXT,
            subject       TEXT,
            body_template TEXT NOT NULL,
            created_by    TEXT,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Visa packages (linked to hotel_records) ────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS visa_packages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            country         TEXT NOT NULL,
            visa_type       TEXT NOT NULL,
            processing_time TEXT,
            validity        TEXT,
            base_price      REAL DEFAULT 0,
            documents_json  TEXT,
            notes           TEXT,
            hotel_ids_json  TEXT,
            created_by      TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Application milestones (stall detection) ──────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS application_milestones (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id               TEXT NOT NULL REFERENCES applications(app_id),
            milestone            TEXT NOT NULL,
            entered_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
            exited_at            DATETIME,
            stall_flagged        INTEGER DEFAULT 0,
            stall_threshold_days INTEGER DEFAULT 4
        )
    """)

    # ── PERMANENT SUPERADMIN — INSERT OR IGNORE so redeploys never reset it ───
    from auth import hash_password
    admin_email = os.getenv("SUPERADMIN_EMAIL", "admin@uniglobemkov.in")
    admin_name  = os.getenv("SUPERADMIN_NAME",  "Admin")
    admin_pass  = os.getenv("SUPERADMIN_PASS",  "MkovAdmin@2026")

    c.execute("""
        INSERT OR IGNORE INTO admin_users (email, name, password, role, active)
        VALUES (?, ?, ?, 'superadmin', 1)
    """, (admin_email, admin_name, hash_password(admin_pass)))

    conn.commit()
    conn.close()
    print(f"✓ Turso DB initialised — superadmin: {admin_email}")
