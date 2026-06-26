"""
database.py — Visa System with Turso (libSQL) cloud database
No demo/seed data — production ready
"""

import sqlite3
import os
import libsql_experimental as libsql


def get_db():
    conn = libsql.connect(
        database=os.getenv("TURSO_DATABASE_URL"),
        auth_token=os.getenv("TURSO_AUTH_TOKEN")
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

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

    c.execute("""
        CREATE TABLE IF NOT EXISTS visa_requirements (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            country_code     TEXT UNIQUE NOT NULL,
            country_name     TEXT NOT NULL,
            visa_types_json  TEXT,
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS custom_checklists (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            country             TEXT NOT NULL,
            visa_type           TEXT NOT NULL,
            name                TEXT,
            description         TEXT,
            documents_json      TEXT NOT NULL,
            base_price          DECIMAL(10,2) DEFAULT 0,
            discount_percentage DECIMAL(5,2) DEFAULT 0,
            final_price         DECIMAL(10,2),
            is_default          INTEGER DEFAULT 0,
            created_by          INTEGER REFERENCES admin_users(id),
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS client_discounts (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id      INTEGER NOT NULL REFERENCES clients(id),
            checklist_id   INTEGER REFERENCES custom_checklists(id),
            discount_type  TEXT,
            discount_value DECIMAL(10,2),
            reason         TEXT,
            active         INTEGER DEFAULT 1,
            created_by     INTEGER REFERENCES admin_users(id),
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

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

    c.execute("""
        CREATE TABLE IF NOT EXISTS communication_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id         TEXT,
            client_id      INTEGER REFERENCES clients(id),
            channel        TEXT NOT NULL,
            phone_number   TEXT,
            email_address  TEXT,
            message_type   TEXT,
            message_content TEXT,
            sent_status    TEXT DEFAULT 'pending',
            response       TEXT,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

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

    c.execute("""
        CREATE TABLE IF NOT EXISTS staff_activity_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id    INTEGER REFERENCES admin_users(id),
            staff_name  TEXT NOT NULL,
            staff_role  TEXT,
            action      TEXT NOT NULL,
            detail      TEXT,
            ip_address  TEXT,
            session_id  TEXT,
            created_at  DATETIME DEFAULT (datetime('now', '+5 hours', '+30 minutes'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS staff_direct_messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id   INTEGER NOT NULL REFERENCES admin_users(id),
            from_name TEXT NOT NULL,
            to_id     INTEGER NOT NULL REFERENCES admin_users(id),
            to_name   TEXT NOT NULL,
            message   TEXT NOT NULL,
            is_ping   INTEGER DEFAULT 0,
            read_at   DATETIME,
            created_at DATETIME DEFAULT (datetime('now', '+5 hours', '+30 minutes'))
        )
    """)

    conn.commit()
    conn.close()
    print("✓ Visa system DB initialised via Turso")
