"""
notifier.py — Direct automation (no n8n needed)
Replaces n8n_hooks.py entirely.

Handles:
  - WhatsApp messages via Meta Business API
  - Email via Gmail SMTP
  - All events: new application, status change, doc reminder

Setup (add these to Render environment variables):

  WHATSAPP_TOKEN       = your Meta permanent access token
  WHATSAPP_PHONE_ID    = your Meta phone number ID
  GMAIL_ADDRESS        = your Gmail address (e.g. noreply@uniglobemkov.in)
  GMAIL_APP_PASSWORD   = your 16-char Gmail app password

If any of these are missing, that channel is silently skipped.
Everything is always logged to the webhook_log DB table.
"""

import os
import json
import smtplib
import requests
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import get_db

# ── Credentials from environment ─────────────────────────────────────────────
WA_TOKEN    = os.getenv("WHATSAPP_TOKEN",    "")
WA_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
GMAIL_ADDR  = os.getenv("GMAIL_ADDRESS",     "")
GMAIL_PASS  = os.getenv("GMAIL_APP_PASSWORD","")

# ── Status messages shown to clients ─────────────────────────────────────────
STATUS_MESSAGES = {
    "pending":       "We are awaiting your documents. Please check your document checklist and upload the required files.",
    "docs_received": "We have received your documents and our team is reviewing them.",
    "review":        "Your application is currently under review by our visa specialists.",
    "submitted":     "Great news! Your application has been submitted to the embassy. Please allow 5–7 working days.",
    "approved":      "Congratulations! 🎉 Your visa has been approved. Please contact us to collect your documents.",
    "rejected":      "We regret to inform you that your visa application was not approved this time. Please contact us to discuss next steps.",
}

DOC_CHECKLIST = {
    "tourist":  ["Passport (front page)", "Recent passport-size photo", "3-month bank statement", "Hotel booking confirmation", "Return flight ticket", "Travel insurance"],
    "business": ["Passport (front page)", "Recent passport-size photo", "3-month bank statement", "Invitation letter", "Return flight ticket", "Company letter"],
    "student":  ["Passport (front page)", "Recent passport-size photo", "3-month bank statement", "University admission letter", "Return flight ticket", "Accommodation proof"],
    "transit":  ["Passport (front page)", "Recent passport-size photo", "Onward ticket"],
}


# ── Internal log to DB ────────────────────────────────────────────────────────
def _log(event: str, payload: dict, status: str):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO webhook_log (event, payload, status) VALUES (?, ?, ?)",
            (event, json.dumps(payload), status)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[NOTIFIER] DB log error: {e}")


# ── WhatsApp ──────────────────────────────────────────────────────────────────
def _send_whatsapp(phone: str, message: str, event: str):
    if not WA_TOKEN or not WA_PHONE_ID:
        print(f"[NOTIFIER] WhatsApp not configured — skipping ({event})")
        return False

    # Normalize phone: must start with country code, no + or spaces
    phone = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    if not phone:
        print(f"[NOTIFIER] No phone number — skipping WhatsApp")
        return False

    url = f"https://graph.facebook.com/v18.0/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type":  "application/json",
    }
    body = {
        "messaging_product": "whatsapp",
        "to":                phone,
        "type":              "text",
        "text":              {"body": message},
    }

    try:
        r = requests.post(url, headers=headers, json=body, timeout=10)
        if r.status_code == 200:
            print(f"[NOTIFIER] ✓ WhatsApp sent to {phone}")
            return True
        else:
            print(f"[NOTIFIER] ✗ WhatsApp failed: {r.status_code} {r.text}")
            return False
    except Exception as e:
        print(f"[NOTIFIER] ✗ WhatsApp error: {e}")
        return False


# ── Email ─────────────────────────────────────────────────────────────────────
def _send_email(to_email: str, subject: str, body_text: str, body_html: str, event: str):
    if not GMAIL_ADDR or not GMAIL_PASS:
        print(f"[NOTIFIER] Email not configured — skipping ({event})")
        return False

    if not to_email:
        print(f"[NOTIFIER] No email address — skipping email")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Uniglobe MKOV Travel <{GMAIL_ADDR}>"
        msg["To"]      = to_email

        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_ADDR, GMAIL_PASS)
            server.sendmail(GMAIL_ADDR, to_email, msg.as_string())

        print(f"[NOTIFIER] ✓ Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"[NOTIFIER] ✗ Email error: {e}")
        return False


# ── Run notifications in background thread ────────────────────────────────────
def _notify_async(fn):
    """Run notification in background so API doesn't wait for it."""
    t = threading.Thread(target=fn, daemon=True)
    t.start()


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC EVENT FUNCTIONS — called from main.py
# ══════════════════════════════════════════════════════════════════════════════

def on_new_application(app_id: str, client_name: str, client_phone: str,
                       client_email: str, destination: str, visa_type: str):
    """
    Called when admin creates a new visa application.
    Sends document checklist via WhatsApp + email.
    """
    checklist = DOC_CHECKLIST.get(visa_type.lower(), DOC_CHECKLIST["tourist"])
    checklist_text = "\n".join(f"  • {doc}" for doc in checklist)
    checklist_bullets = "".join(f"<li>{doc}</li>" for doc in checklist)

    wa_message = (
        f"Namaste {client_name}! 🙏\n\n"
        f"Your visa application has been created with Uniglobe MKOV Travel.\n\n"
        f"📋 *Application ID:* {app_id}\n"
        f"🌍 *Destination:* {destination}\n"
        f"🛂 *Visa Type:* {visa_type.title()}\n\n"
        f"Please arrange the following documents:\n"
        f"{checklist_text}\n\n"
        f"Upload your documents at:\n"
        f"https://arya-v1-0-0.onrender.com/client\n\n"
        f"Login: {client_email}\n\n"
        f"Need help? Call us: +91-8010700700\n"
        f"*Uniglobe MKOV Travel*"
    )

    email_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px">
      <div style="background:linear-gradient(135deg,#0d3055,#1a5a8a);padding:24px;border-radius:8px 8px 0 0;text-align:center">
        <h1 style="color:white;margin:0;font-size:22px">Uniglobe MKOV Travel</h1>
        <p style="color:rgba(255,255,255,0.8);margin:6px 0 0">Visa Application Created</p>
      </div>
      <div style="background:#f9f9f9;padding:24px;border:1px solid #e0e0e0">
        <p style="font-size:16px">Dear <strong>{client_name}</strong>,</p>
        <p>Thank you for choosing Uniglobe MKOV Travel. Your visa application has been created.</p>
        <div style="background:white;border:1px solid #e0e0e0;border-radius:8px;padding:16px;margin:16px 0">
          <p><strong>Application ID:</strong> {app_id}</p>
          <p><strong>Destination:</strong> {destination}</p>
          <p><strong>Visa Type:</strong> {visa_type.title()}</p>
        </div>
        <p><strong>Please submit the following documents:</strong></p>
        <ul style="line-height:2">{checklist_bullets}</ul>
        <div style="text-align:center;margin:24px 0">
          <a href="https://arya-v1-0-0.onrender.com/client"
             style="background:#0d3055;color:white;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:bold">
            Upload Documents →
          </a>
        </div>
        <p style="font-size:13px;color:#666">Login email: {client_email}</p>
        <p style="font-size:13px;color:#666">Need help? Call +91-8010700700 or reply to this email.</p>
      </div>
      <div style="background:#0d3055;padding:12px;border-radius:0 0 8px 8px;text-align:center">
        <p style="color:rgba(255,255,255,0.7);font-size:12px;margin:0">Uniglobe MKOV Travel · Noida, India</p>
      </div>
    </div>
    """

    email_text = (
        f"Dear {client_name},\n\n"
        f"Your visa application has been created.\n"
        f"Application ID: {app_id}\n"
        f"Destination: {destination}\n"
        f"Visa Type: {visa_type.title()}\n\n"
        f"Documents required:\n{checklist_text}\n\n"
        f"Upload at: https://arya-v1-0-0.onrender.com/client\n"
        f"Login: {client_email}\n\n"
        f"Uniglobe MKOV Travel\n+91-8010700700"
    )

    payload = {"app_id": app_id, "client_name": client_name, "event": "new_application"}

    def _run():
        wa_ok    = _send_whatsapp(client_phone, wa_message, "new_application")
        email_ok = _send_email(
            client_email,
            f"Visa Application Created — {app_id} — Documents Required",
            email_text, email_html, "new_application"
        )
        _log("new_application", payload, "sent" if (wa_ok or email_ok) else "failed")

    _notify_async(_run)


def on_status_change(app_id: str, client_name: str, client_phone: str,
                     client_email: str, old_status: str, new_status: str, note: str = ""):
    """
    Called when admin updates visa application status.
    Sends status update via WhatsApp + email.
    """
    message = STATUS_MESSAGES.get(new_status, f"Your application status has been updated to: {new_status}.")
    status_label = new_status.replace("_", " ").title()

    STATUS_EMOJI = {
        "pending":       "⏳",
        "docs_received": "📥",
        "review":        "🔍",
        "submitted":     "📤",
        "approved":      "✅",
        "rejected":      "❌",
    }
    emoji = STATUS_EMOJI.get(new_status, "🔄")

    wa_message = (
        f"Hello {client_name}! {emoji}\n\n"
        f"Your visa application status has been updated.\n\n"
        f"📋 *Application:* {app_id}\n"
        f"🔄 *Status:* {status_label}\n\n"
        f"{message}\n"
        + (f"\n📝 Note: {note}\n" if note else "") +
        f"\nView your application:\n"
        f"https://arya-v1-0-0.onrender.com/client\n\n"
        f"Questions? Call +91-8010700700\n"
        f"*Uniglobe MKOV Travel*"
    )

    email_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px">
      <div style="background:linear-gradient(135deg,#0d3055,#1a5a8a);padding:24px;border-radius:8px 8px 0 0;text-align:center">
        <h1 style="color:white;margin:0;font-size:22px">Uniglobe MKOV Travel</h1>
        <p style="color:rgba(255,255,255,0.8);margin:6px 0 0">Visa Application Update</p>
      </div>
      <div style="background:#f9f9f9;padding:24px;border:1px solid #e0e0e0">
        <p style="font-size:16px">Dear <strong>{client_name}</strong>,</p>
        <p>Your visa application status has been updated.</p>
        <div style="background:white;border:1px solid #e0e0e0;border-radius:8px;padding:16px;margin:16px 0;text-align:center">
          <p style="font-size:28px;margin:0">{emoji}</p>
          <p style="font-size:20px;font-weight:bold;color:#0d3055;margin:8px 0">{status_label}</p>
          <p style="color:#555;margin:0"><strong>{app_id}</strong></p>
        </div>
        <p style="font-size:15px">{message}</p>
        {"<p style='background:#fff3cd;padding:12px;border-radius:6px;border-left:4px solid #e8b84b'><strong>Note:</strong> " + note + "</p>" if note else ""}
        <div style="text-align:center;margin:24px 0">
          <a href="https://arya-v1-0-0.onrender.com/client"
             style="background:#0d3055;color:white;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:bold">
            View Application →
          </a>
        </div>
        <p style="font-size:13px;color:#666">Need help? Call +91-8010700700 or reply to this email.</p>
      </div>
      <div style="background:#0d3055;padding:12px;border-radius:0 0 8px 8px;text-align:center">
        <p style="color:rgba(255,255,255,0.7);font-size:12px;margin:0">Uniglobe MKOV Travel · Noida, India</p>
      </div>
    </div>
    """

    email_text = (
        f"Dear {client_name},\n\n"
        f"Your visa application status has been updated.\n\n"
        f"Application: {app_id}\n"
        f"New Status: {status_label}\n\n"
        f"{message}\n"
        + (f"\nNote: {note}\n" if note else "") +
        f"\nView your application: https://arya-v1-0-0.onrender.com/client\n\n"
        f"Uniglobe MKOV Travel\n+91-8010700700"
    )

    payload = {
        "app_id": app_id, "client_name": client_name,
        "old_status": old_status, "new_status": new_status
    }

    def _run():
        wa_ok    = _send_whatsapp(client_phone, wa_message, "status_change")
        email_ok = _send_email(
            client_email,
            f"Visa Update — {app_id} — {status_label}",
            email_text, email_html, "status_change"
        )
        _log("status_change", payload, "sent" if (wa_ok or email_ok) else "failed")

    _notify_async(_run)


def on_docs_reminder(app_id: str, client_name: str, client_phone: str,
                     client_email: str, missing_docs: list):
    """
    Called manually or by a scheduled reminder.
    Sends reminder about missing documents.
    """
    docs_text = "\n".join(f"  • {doc}" for doc in missing_docs)
    docs_bullets = "".join(f"<li>{doc}</li>" for doc in missing_docs)

    wa_message = (
        f"Hi {client_name}! 🔔\n\n"
        f"This is a friendly reminder from Uniglobe MKOV Travel.\n\n"
        f"We are still waiting for the following documents for your application *{app_id}*:\n\n"
        f"{docs_text}\n\n"
        f"Please upload them at your earliest:\n"
        f"https://arya-v1-0-0.onrender.com/client\n\n"
        f"Need help? Call +91-8010700700\n"
        f"*Uniglobe MKOV Travel*"
    )

    email_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px">
      <div style="background:linear-gradient(135deg,#0d3055,#1a5a8a);padding:24px;border-radius:8px 8px 0 0;text-align:center">
        <h1 style="color:white;margin:0;font-size:22px">Uniglobe MKOV Travel</h1>
        <p style="color:rgba(255,255,255,0.8);margin:6px 0 0">Document Reminder</p>
      </div>
      <div style="background:#f9f9f9;padding:24px;border:1px solid #e0e0e0">
        <p style="font-size:16px">Dear <strong>{client_name}</strong>,</p>
        <p>We are still waiting for the following documents for your application <strong>{app_id}</strong>:</p>
        <ul style="line-height:2;background:white;padding:16px 16px 16px 36px;border-radius:8px;border:1px solid #e0e0e0">
          {docs_bullets}
        </ul>
        <p>Please upload them as soon as possible to avoid delays in your application.</p>
        <div style="text-align:center;margin:24px 0">
          <a href="https://arya-v1-0-0.onrender.com/client"
             style="background:#0d3055;color:white;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:bold">
            Upload Documents →
          </a>
        </div>
        <p style="font-size:13px;color:#666">Need help? Call +91-8010700700</p>
      </div>
      <div style="background:#0d3055;padding:12px;border-radius:0 0 8px 8px;text-align:center">
        <p style="color:rgba(255,255,255,0.7);font-size:12px;margin:0">Uniglobe MKOV Travel · Noida, India</p>
      </div>
    </div>
    """

    email_text = (
        f"Dear {client_name},\n\n"
        f"We are still waiting for the following documents:\n{docs_text}\n\n"
        f"Upload at: https://arya-v1-0-0.onrender.com/client\n\n"
        f"Uniglobe MKOV Travel\n+91-8010700700"
    )

    payload = {"app_id": app_id, "client_name": client_name, "missing_docs": missing_docs}

    def _run():
        wa_ok    = _send_whatsapp(client_phone, wa_message, "docs_reminder")
        email_ok = _send_email(
            client_email,
            f"Documents Required — {app_id}",
            email_text, email_html, "docs_reminder"
        )
        _log("docs_reminder", payload, "sent" if (wa_ok or email_ok) else "failed")

    _notify_async(_run)
