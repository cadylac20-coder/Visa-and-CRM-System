"""
notifier_enhanced.py
WhatsApp + Email + SMS support
Replaces notifier.py with SMS functionality added
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
WA_TOKEN         = os.getenv("WHATSAPP_TOKEN",      "")
WA_PHONE_ID      = os.getenv("WHATSAPP_PHONE_ID",   "")
GMAIL_ADDR       = os.getenv("GMAIL_ADDRESS",       "")
GMAIL_PASS       = os.getenv("GMAIL_APP_PASSWORD",  "")
TWILIO_SID       = os.getenv("TWILIO_ACCOUNT_SID",  "")
TWILIO_AUTH      = os.getenv("TWILIO_AUTH_TOKEN",   "")
TWILIO_PHONE     = os.getenv("TWILIO_PHONE_NUMBER", "")  # e.g. +15551234567

# ── Status messages ───────────────────────────────────────────────────────────
STATUS_MESSAGES = {
    "pending":       "We are awaiting your documents. Please check your document checklist.",
    "docs_received": "We have received your documents and our team is reviewing them.",
    "review":        "Your application is under review by our visa specialists.",
    "submitted":     "Your application has been submitted to the embassy. Allow 5–7 working days.",
    "approved":      "Congratulations! 🎉 Your visa has been approved.",
    "rejected":      "We regret to inform you that your visa application was not approved.",
}

DOC_CHECKLIST = {
    "tourist":  ["Passport", "Photo", "Bank Statement", "Hotel Booking", "Return Flight"],
    "business": ["Passport", "Photo", "Bank Statement", "Invitation", "Return Flight"],
    "student":  ["Passport", "Photo", "Bank Statement", "Admission Letter", "Return Flight"],
}


def _log(event: str, payload: dict, status: str, channel: str = ""):
    """Log to DB."""
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO webhook_log (event, payload, status) VALUES (?, ?, ?)",
            (event, json.dumps(payload), status)
        )
        # FIXED (correct columns, matches DB schema)
    if channel:
        conn.execute(
            "INSERT INTO communication_log (channel, message_type, sent_status) VALUES (?, ?, ?)",
            (channel, event, status)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[NOTIFIER] DB log error: {e}")


# ── WhatsApp ──────────────────────────────────────────────────────────────────
def _send_whatsapp(phone: str, message: str, event: str):
    if not WA_TOKEN or not WA_PHONE_ID:
        print(f"[NOTIFIER] WhatsApp not configured — skipping")
        return False

    phone = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    if not phone:
        return False

    url = f"https://graph.facebook.com/v18.0/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message},
    }

    try:
        r = requests.post(url, headers=headers, json=body, timeout=10)
        if r.status_code == 200:
            print(f"[NOTIFIER] ✓ WhatsApp sent to {phone}")
            _log(event, {"phone": phone}, "sent", "whatsapp")
            return True
        else:
            print(f"[NOTIFIER] ✗ WhatsApp failed: {r.status_code}")
            _log(event, {"phone": phone}, "failed", "whatsapp")
            return False
    except Exception as e:
        print(f"[NOTIFIER] ✗ WhatsApp error: {e}")
        _log(event, {"phone": phone}, "failed", "whatsapp")
        return False


# ── SMS via Twilio ───────────────────────────────────────────────────────────
def _send_sms(phone: str, message: str, event: str):
    if not TWILIO_SID or not TWILIO_AUTH or not TWILIO_PHONE:
        print(f"[NOTIFIER] SMS not configured — skipping")
        return False

    phone = phone.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+91" + phone  # assume India if no country code

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
    auth = (TWILIO_SID, TWILIO_AUTH)
    data = {
        "From": TWILIO_PHONE,
        "To": phone,
        "Body": message,
    }

    try:
        r = requests.post(url, auth=auth, data=data, timeout=10)
        if r.status_code in [200, 201]:
            print(f"[NOTIFIER] ✓ SMS sent to {phone}")
            _log(event, {"phone": phone}, "sent", "sms")
            return True
        else:
            print(f"[NOTIFIER] ✗ SMS failed: {r.status_code}")
            _log(event, {"phone": phone}, "failed", "sms")
            return False
    except Exception as e:
        print(f"[NOTIFIER] ✗ SMS error: {e}")
        _log(event, {"phone": phone}, "failed", "sms")
        return False


# ── Email ─────────────────────────────────────────────────────────────────────
def _send_email(to_email: str, subject: str, body_text: str, body_html: str, event: str):
    if not GMAIL_ADDR or not GMAIL_PASS:
        print(f"[NOTIFIER] Email not configured — skipping")
        return False

    if not to_email:
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Uniglobe MKOV Travel <{GMAIL_ADDR}>"
        msg["To"] = to_email

        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_ADDR, GMAIL_PASS)
            server.sendmail(GMAIL_ADDR, to_email, msg.as_string())

        print(f"[NOTIFIER] ✓ Email sent to {to_email}")
        _log(event, {"email": to_email}, "sent", "email")
        return True
    except Exception as e:
        print(f"[NOTIFIER] ✗ Email error: {e}")
        _log(event, {"email": to_email}, "failed", "email")
        return False


def _notify_async(fn):
    """Run in background thread."""
    t = threading.Thread(target=fn, daemon=True)
    t.start()


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def send_checklist(
    client_name: str,
    client_phone: str,
    client_email: str,
    app_id: str,
    destination: str,
    visa_type: str,
    checklist_items: list,
    checklist_price: float = 0,
    channels: list = None,  # ['whatsapp', 'sms', 'email']
):
    """
    Send document checklist to client via chosen channels.
    """
    if channels is None:
        channels = ["whatsapp", "email"]  # default

    checklist_text = "\n".join(f"  • {item}" for item in checklist_items)
    checklist_html = "".join(f"<li>{item}</li>" for item in checklist_items)

    wa_message = (
        f"Hi {client_name}! 🙏\n\n"
        f"Your visa application for {destination} ({visa_type.title()}) has been created.\n"
        f"📋 Application ID: {app_id}\n\n"
        f"Please arrange:\n{checklist_text}\n\n"
        f"Upload at: https://arya-v1-0-0.onrender.com/client\n"
        f"Need help? +91-8010700700\n"
        f"Uniglobe MKOV Travel"
    )

    sms_message = (
        f"Hi {client_name}! Your visa app {app_id} created for {destination}. "
        f"Upload documents at https://arya-v1-0-0.onrender.com/client Call: 8010700700"
    )

    email_html = f"""
    <div style="font-family:Arial;max-width:600px;margin:auto;padding:20px">
      <div style="background:#0d3055;color:white;padding:24px;border-radius:8px 8px 0 0">
        <h1 style="margin:0">Uniglobe MKOV Travel</h1>
        <p style="opacity:0.8;margin:6px 0 0">Visa Application Created</p>
      </div>
      <div style="background:#f9f9f9;padding:24px;border:1px solid #e0e0e0">
        <p>Dear <strong>{client_name}</strong>,</p>
        <p>Your visa application has been created successfully.</p>
        <div style="background:white;padding:16px;border:1px solid #e0e0e0;border-radius:8px;margin:16px 0">
          <p><strong>Application ID:</strong> {app_id}</p>
          <p><strong>Destination:</strong> {destination}</p>
          <p><strong>Visa Type:</strong> {visa_type.title()}</p>
          {"<p><strong>Service Charge:</strong> ₹" + str(checklist_price) + "</p>" if checklist_price else ""}
        </div>
        <p><strong>Required Documents:</strong></p>
        <ul style="line-height:1.8">{checklist_html}</ul>
        <div style="text-align:center;margin:24px 0">
          <a href="https://arya-v1-0-0.onrender.com/client" 
             style="background:#0d3055;color:white;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:bold">
            Upload Documents →
          </a>
        </div>
        <p style="font-size:12px;color:#666">Need help? Call +91-8010700700</p>
      </div>
    </div>
    """

    email_text = (
        f"Dear {client_name},\n\n"
        f"Your visa application {app_id} created for {destination} ({visa_type}).\n\n"
        f"Documents needed:\n{checklist_text}\n\n"
        f"Upload at: https://arya-v1-0-0.onrender.com/client\n"
        f"Call: +91-8010700700\n\n"
        f"Uniglobe MKOV Travel"
    )

    def _run():
        success = False
        if "whatsapp" in channels:
            success = _send_whatsapp(client_phone, wa_message, "send_checklist") or success
        if "sms" in channels:
            success = _send_sms(client_phone, sms_message, "send_checklist") or success
        if "email" in channels:
            success = _send_email(
                client_email,
                f"Visa Application Created — {app_id} — Documents Required",
                email_text, email_html, "send_checklist"
            ) or success

    _notify_async(_run)


def send_status_update(
    client_name: str,
    client_phone: str,
    client_email: str,
    app_id: str,
    new_status: str,
    note: str = "",
    channels: list = None,  # ['whatsapp', 'sms', 'email']
):
    """Send status update via chosen channels."""
    if channels is None:
        channels = ["whatsapp", "email"]

    message = STATUS_MESSAGES.get(new_status, f"Status updated to {new_status}")
    emoji = {"approved": "✅", "rejected": "❌", "submitted": "📤", "review": "🔍"}.get(new_status, "🔄")

    wa_message = (
        f"Hello {client_name}! {emoji}\n\n"
        f"Your visa application status updated.\n"
        f"📋 {app_id}\n"
        f"Status: {new_status.replace('_', ' ').title()}\n\n"
        f"{message}\n"
        + (f"\n📝 {note}\n" if note else "") +
        f"\nView: https://arya-v1-0-0.onrender.com/client\n"
        f"Call: +91-8010700700"
    )

    sms_message = (
        f"Hi {client_name}! Your visa {app_id} status: {new_status.replace('_', ' ')}. "
        f"Check https://arya-v1-0-0.onrender.com/client"
    )

    email_html = f"""
    <div style="font-family:Arial;max-width:600px;margin:auto;padding:20px">
      <div style="background:#0d3055;color:white;padding:24px;border-radius:8px 8px 0 0;text-align:center">
        <h1 style="margin:0;font-size:24px">{emoji}</h1>
        <h2 style="margin:8px 0;text-transform:uppercase">{new_status.replace('_', ' ')}</h2>
      </div>
      <div style="background:#f9f9f9;padding:24px;border:1px solid #e0e0e0">
        <p>Dear <strong>{client_name}</strong>,</p>
        <p>{message}</p>
        {"<p style='background:#fff3cd;padding:12px;border-radius:6px'><strong>Note:</strong> " + note + "</p>" if note else ""}
        <div style="text-align:center;margin:24px 0">
          <a href="https://arya-v1-0-0.onrender.com/client"
             style="background:#0d3055;color:white;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:bold">
            View Application →
          </a>
        </div>
      </div>
    </div>
    """

    email_text = f"Dear {client_name},\n\n{message}\n\n{note}\n\nView at https://arya-v1-0-0.onrender.com/client"

    def _run():
        if "whatsapp" in channels:
            _send_whatsapp(client_phone, wa_message, "status_update")
        if "sms" in channels:
            _send_sms(client_phone, sms_message, "status_update")
        if "email" in channels:
            _send_email(client_email, f"Visa Update — {app_id}", email_text, email_html, "status_update")

    _notify_async(_run)


def send_reminder(
    client_name: str,
    client_phone: str,
    client_email: str,
    app_id: str,
    missing_docs: list,
    channels: list = None,
):
    """Send reminder about missing documents."""
    if channels is None:
        channels = ["whatsapp", "email"]

    docs_text = "\n".join(f"  • {doc}" for doc in missing_docs)
    docs_html = "".join(f"<li>{doc}</li>" for doc in missing_docs)

    wa_message = (
        f"Hi {client_name}! 🔔\n\n"
        f"Reminder: We're awaiting documents for {app_id}.\n\n"
        f"Missing:\n{docs_text}\n\n"
        f"Upload: https://arya-v1-0-0.onrender.com/client\n"
        f"Call: +91-8010700700"
    )

    sms_message = (
        f"Hi {client_name}, reminder: upload missing documents for {app_id} "
        f"at https://arya-v1-0-0.onrender.com/client"
    )

    email_html = f"""
    <div style="font-family:Arial;max-width:600px;margin:auto;padding:20px">
      <div style="background:#0d3055;color:white;padding:24px;border-radius:8px 8px 0 0">
        <h1 style="margin:0">Document Reminder</h1>
      </div>
      <div style="background:#f9f9f9;padding:24px;border:1px solid #e0e0e0">
        <p>Dear {client_name},</p>
        <p>We're still waiting for the following documents:</p>
        <ul style="line-height:1.8">{docs_html}</ul>
        <div style="text-align:center;margin:24px 0">
          <a href="https://arya-v1-0-0.onrender.com/client"
             style="background:#0d3055;color:white;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:bold">
            Upload Now →
          </a>
        </div>
      </div>
    </div>
    """

    email_text = f"Dear {client_name},\n\nPlease upload:\n{docs_text}\n\nAt https://arya-v1-0-0.onrender.com/client"

    def _run():
        if "whatsapp" in channels:
            _send_whatsapp(client_phone, wa_message, "docs_reminder")
        if "sms" in channels:
            _send_sms(client_phone, sms_message, "docs_reminder")
        if "email" in channels:
            _send_email(client_email, f"Documents Required — {app_id}", email_text, email_html, "docs_reminder")

    _notify_async(_run)
