"""
n8n webhook integration.
When a status changes, we fire a POST to n8n which then:
  - Sends WhatsApp message via WhatsApp Business API
  - Sends email via Gmail node
  - Updates Google Sheets dashboard
  - Triggers reminders via Cron node if needed

To enable: set N8N_WEBHOOK_URL in your .env
If not set, events are only logged locally (no external calls).
"""

import os
import json
import requests
from database import get_db

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")  # e.g. http://localhost:5678/webhook/visa-status


def fire_webhook(event: str, payload: dict):
    """
    Fire an n8n webhook event.
    Always logs to DB. Only makes HTTP call if N8N_WEBHOOK_URL is set.
    """
    conn = get_db()
    conn.execute(
        "INSERT INTO webhook_log (event, payload, status) VALUES (?, ?, ?)",
        (event, json.dumps(payload), "pending" if N8N_WEBHOOK_URL else "disabled")
    )
    conn.commit()

    if not N8N_WEBHOOK_URL:
        print(f"[n8n] Webhook disabled — event logged: {event}")
        conn.close()
        return

    try:
        r = requests.post(
            N8N_WEBHOOK_URL,
            json={"event": event, **payload},
            timeout=5
        )
        status = "sent" if r.status_code < 400 else "failed"
        conn.execute(
            "UPDATE webhook_log SET status=? WHERE id=(SELECT MAX(id) FROM webhook_log)",
            (status,)
        )
        conn.commit()
        print(f"[n8n] Webhook fired: {event} → {r.status_code}")
    except Exception as e:
        conn.execute(
            "UPDATE webhook_log SET status='failed' WHERE id=(SELECT MAX(id) FROM webhook_log)",
            ()
        )
        conn.commit()
        print(f"[n8n] Webhook error: {e}")
    finally:
        conn.close()


# ── Event helpers ─────────────────────────────────────────────────────────────

def on_new_application(app_id: str, client_name: str, client_phone: str,
                       destination: str, visa_type: str):
    fire_webhook("new_application", {
        "app_id": app_id,
        "client_name": client_name,
        "client_phone": client_phone,
        "destination": destination,
        "visa_type": visa_type,
        "action": "send_checklist",
    })


def on_status_change(app_id: str, client_name: str, client_phone: str,
                     client_email: str, old_status: str, new_status: str, note: str = ""):
    STATUS_MESSAGES = {
        "docs_received": "We have received your documents and are reviewing them.",
        "review":        "Your application is currently under review by our team.",
        "submitted":     "Great news! Your application has been submitted to the embassy.",
        "approved":      "Congratulations! Your visa has been approved.",
        "rejected":      "We regret to inform you that your visa application was not approved. Please contact us.",
        "pending":       "We are awaiting some documents from you. Please check your document checklist.",
    }
    fire_webhook("status_change", {
        "app_id":       app_id,
        "client_name":  client_name,
        "client_phone": client_phone,
        "client_email": client_email,
        "old_status":   old_status,
        "new_status":   new_status,
        "message":      STATUS_MESSAGES.get(new_status, f"Status updated to: {new_status}"),
        "note":         note,
    })


def on_docs_reminder(app_id: str, client_name: str, client_phone: str, missing_docs: list):
    fire_webhook("docs_reminder", {
        "app_id":       app_id,
        "client_name":  client_name,
        "client_phone": client_phone,
        "missing_docs": missing_docs,
        "action":       "send_reminder",
    })
