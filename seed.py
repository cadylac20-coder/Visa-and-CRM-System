"""
Run this once after init_db() to seed demo data.
python seed.py
"""

from database import init_db, get_db
from auth import hash_password
from datetime import datetime

init_db()
conn = get_db()

# ── Demo clients ──────────────────────────────────────────────────────────────
clients = [
    ("Rahul Sharma",  "rahul.sharma@email.com",  "+91 98765 43210", "rahul2024"),
    ("Priya Mehta",   "priya.mehta@email.com",   "+91 87654 32109", "priya2024"),
    ("Amit Verma",    "amit.verma@email.com",    "+91 76543 21098", "amit2024"),
    ("Sneha Kapoor",  "sneha.kapoor@email.com",  "+91 65432 10987", "sneha2024"),
]

for name, email, phone, pw in clients:
    conn.execute(
        "INSERT OR IGNORE INTO clients (name, email, phone, password) VALUES (?,?,?,?)",
        (name, email, phone, hash_password(pw))
    )

conn.commit()

# ── Demo applications ─────────────────────────────────────────────────────────
apps = [
    ("VIS-2026-001", "rahul.sharma@email.com",  "Dubai",     "tourist",  "2026-07-15", "submitted", 75),
    ("VIS-2026-002", "priya.mehta@email.com",   "Thailand",  "tourist",  "2026-07-20", "review",    55),
    ("VIS-2026-003", "amit.verma@email.com",    "Schengen",  "business", "2026-06-01", "approved",  100),
    ("VIS-2026-004", "sneha.kapoor@email.com",  "Singapore", "tourist",  "2026-08-01", "pending",   10),
]

doc_sets = {
    "tourist":  ["passport","photo","bank_statement","hotel_booking","flight_ticket","travel_insurance"],
    "business": ["passport","photo","bank_statement","invitation_letter","flight_ticket","company_letter"],
}

status_map = {
    "submitted": ["verified","verified","verified","verified","verified","missing"],
    "review":    ["verified","verified","verified","verified","missing","missing"],
    "approved":  ["verified","verified","verified","verified","verified","verified"],
    "pending":   ["missing","missing","missing","missing","missing","missing"],
}

for app_id, email, dest, vtype, tdate, status, progress in apps:
    c = conn.execute("SELECT id FROM clients WHERE email=?", (email,)).fetchone()
    if not c:
        continue
    conn.execute("""
        INSERT OR IGNORE INTO applications
            (app_id, client_id, destination, visa_type, travel_date, status, progress)
        VALUES (?,?,?,?,?,?,?)
    """, (app_id, c["id"], dest, vtype, tdate, status, progress))

    docs     = doc_sets.get(vtype, doc_sets["tourist"])
    statuses = status_map.get(status, status_map["pending"])

    for doc_type, doc_status in zip(docs, statuses):
        conn.execute("""
            INSERT OR IGNORE INTO documents (app_id, doc_type, status)
            VALUES (?,?,?)
        """, (app_id, doc_type, doc_status))

    # Activity log
    log_entries = {
        "pending":   [("system","Application created","Checklist sent via WhatsApp"),
                      ("system","Awaiting documents","Reminder scheduled in 48hrs")],
        "review":    [("system","Application created","Checklist sent"),
                      ("admin:Admin","Docs received","Documents uploaded and under review")],
        "submitted": [("system","Application created","Checklist sent"),
                      ("admin:Admin","Docs verified","All documents verified"),
                      ("admin:Admin","Status updated","Submitted to embassy")],
        "approved":  [("system","Application created","Checklist sent"),
                      ("admin:Admin","Docs verified","Documents verified"),
                      ("admin:Admin","Submitted","Submitted to embassy"),
                      ("admin:Admin","Approved","Visa approved — 90 days")],
    }
    for actor, action, detail in log_entries.get(status, []):
        conn.execute("""
            INSERT OR IGNORE INTO activity_log (app_id, actor, action, detail)
            VALUES (?,?,?,?)
        """, (app_id, actor, action, detail))

    # Notification for client
    notif_msg = {
        "pending":   "Welcome! Your application is created. Please upload your documents.",
        "review":    "We have received your documents and are reviewing your application.",
        "submitted": "Your application has been submitted to the embassy. Decision expected in 5-7 days.",
        "approved":  "Congratulations! Your visa has been approved. Passport dispatch in 24hrs.",
    }
    conn.execute("""
        INSERT OR IGNORE INTO notifications (client_id, app_id, message)
        VALUES (?,?,?)
    """, (c["id"], app_id, notif_msg.get(status,"")))

conn.commit()
conn.close()
print("✓ Demo data seeded successfully")
print("  Admin login:  admin@uniglobemkov.in / admin123")
print("  Client login: rahul.sharma@email.com / rahul2024")
print("  Client login: priya.mehta@email.com  / priya2024")
print("  Client login: sneha.kapoor@email.com / sneha2024")
