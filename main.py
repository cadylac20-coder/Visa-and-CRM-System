"""
MKOV Visa Automation System — main.py (COMPLETE UPDATED VERSION v2.0)
"""
import os
import uuid
import json
import shutil
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

# All timestamps in this system are in IST (Asia/Kolkata, UTC+5:30)
IST = ZoneInfo("Asia/Kolkata")

def now_ist() -> datetime:
    """Return current datetime in IST."""
    return datetime.now(tz=IST)

def now_ist_str(fmt: str = "%Y-%m-%dT%H:%M:%S") -> str:
    return now_ist().strftime(fmt)
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional

from database import init_db, get_db
from auth import require_admin, require_client, require_superadmin, require_roles, admin_login, client_login, hash_password
from notifier import send_checklist, send_status_update, send_reminder, send_calendar_reminder

init_db()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="MKOV Visa System", version="2.0.0", docs_url="/docs")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

STATUS_PROGRESS = {
    "pending": 10, "docs_received": 35, "review": 55,
    "submitted": 75, "approved": 100, "rejected": 0,
}

# --- Schemas ───────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str

class NewApplicationRequest(BaseModel):
    client_email:  str
    destination:   str
    visa_type:     str
    travel_date:   Optional[str] = None
    duration_days: Optional[int] = None
    group_size:    int = 1
    checklist_id:  Optional[int] = None
    client_name:   Optional[str] = None   # used if client doesn't exist yet
    client_phone:  Optional[str] = None   # used if client doesn't exist yet

class UpdateStatusRequest(BaseModel):
    status:   str
    note:     Optional[str] = ""
    channels: Optional[list] = ["whatsapp", "email"]

class NewClientRequest(BaseModel):
    name: str; email: str; phone: Optional[str] = ""; password: str
    passport_b64: Optional[str] = None
    passport_filename: Optional[str] = None

class UpdateDocStatusRequest(BaseModel):
    doc_id: int; status: str; notes: Optional[str] = ""

class CountrySearch(BaseModel):
    query: str

class CustomChecklistData(BaseModel):
    country: str; visa_type: str; name: str
    description: Optional[str] = ""
    documents: list
    base_price: float = 0
    discount_percentage: float = 0

class UpdateChecklistData(BaseModel):
    base_price: Optional[float] = None
    discount_percentage: Optional[float] = None
    documents: Optional[list] = None

class ExportChecklistsRequest(BaseModel):
    checklist_ids: list[int]

class ClientDiscountData(BaseModel):
    client_id: int; checklist_id: int
    discount_type: str; discount_value: float; reason: Optional[str] = ""

class SendChecklistRequest(BaseModel):
    app_id: str; channels: list = ["whatsapp", "email"]

class SendStatusRequest(BaseModel):
    app_id: str; new_status: str
    note: Optional[str] = ""; channels: list = ["whatsapp", "email"]

class SendReminderRequest(BaseModel):
    app_id: str; missing_docs: list; channels: list = ["whatsapp", "email"]

# --- Staff management schemas ───────────────────────────────────────────────
class NewStaffRequest(BaseModel):
    name: str; email: str; password: str
    role: str = "sales"   # sales | visa_staff | superadmin

class UpdateStaffRequest(BaseModel):
    name:     Optional[str] = None
    role:     Optional[str] = None
    active:   Optional[int] = None
    password: Optional[str] = None

# --- Leads & follow-up schemas ──────────────────────────────────────────────
class NewLeadRequest(BaseModel):
    name: str; email: Optional[str] = ""; phone: Optional[str] = ""
    destination: Optional[str] = ""; visa_type: Optional[str] = ""
    source: str = "manual"; notes: Optional[str] = ""
    assigned_to: Optional[int] = None

class UpdateLeadRequest(BaseModel):
    name:        Optional[str] = None
    email:       Optional[str] = None
    phone:       Optional[str] = None
    destination: Optional[str] = None
    visa_type:   Optional[str] = None
    status:      Optional[str] = None
    assigned_to: Optional[int] = None
    notes:       Optional[str] = None

class NewFollowupRequest(BaseModel):
    lead_id: int; due_at: str; note: Optional[str] = ""; channel: str = "call"

class ConvertLeadRequest(BaseModel):
    password: str   # client portal password to set on conversion

# --- Calendar schemas ────────────────────────────────────────────────────────
class NewCalendarEventRequest(BaseModel):
    title:      str
    event_type: str = "other"
    start_at:   str
    end_at:     Optional[str] = None
    all_day:    int = 0
    client_id:  Optional[int] = None
    app_id:     Optional[str] = None
    lead_id:    Optional[int] = None
    location:   Optional[str] = ""
    notes:      Optional[str] = ""
    color:      Optional[str] = "#00a99c"
    reminder_minutes_before: Optional[int] = None   # e.g. 1440 = remind 1 day before
    reminder_email:          Optional[str] = None   # defaults to creator's own email if not set

class UpdateCalendarEventRequest(BaseModel):
    title:      Optional[str] = None
    event_type: Optional[str] = None
    start_at:   Optional[str] = None
    end_at:     Optional[str] = None
    all_day:    Optional[int] = None
    location:   Optional[str] = None
    notes:      Optional[str] = None
    color:      Optional[str] = None
    reminder_minutes_before: Optional[int] = None
    reminder_email:          Optional[str] = None

class DismissPopupRequest(BaseModel):
    staff_name: str

class TeamChatMessageRequest(BaseModel):
    message: str

# --- Invoice & payment schemas ───────────────────────────────────────────────
class InvoiceLineItem(BaseModel):
    label: str; qty: float = 1; unit_price: float = 0

class NewInvoiceRequest(BaseModel):
    client_id:    int
    app_id:       Optional[str] = None
    line_items:   list[InvoiceLineItem]
    discount:     float = 0
    tax_percent:  float = 0
    due_date:     Optional[str] = None
    notes:        Optional[str] = ""

class UpdateInvoiceRequest(BaseModel):
    line_items:  Optional[list[InvoiceLineItem]] = None
    discount:    Optional[float] = None
    tax_percent: Optional[float] = None
    due_date:    Optional[str] = None
    notes:       Optional[str] = None
    status:      Optional[str] = None

class RecordPaymentRequest(BaseModel):
    amount:    float
    method:    str = "cash"
    reference: Optional[str] = ""
    paid_at:   Optional[str] = None
    notes:     Optional[str] = ""

# --- Health & Frontend ─────────────────────────────────────────────────────────
@app.get("/")
def root(): return {"status": "online", "service": "MKOV Visa System v2.0.0"}

@app.get("/health")
def health(): return {"status": "ok"}

@app.get("/admin", response_class=HTMLResponse)
def serve_admin():
    path = os.path.join(STATIC_DIR, "admin.html")
    return HTMLResponse(open(path).read()) if os.path.exists(path) else HTMLResponse("Not found", 404)

@app.get("/client", response_class=HTMLResponse)
def serve_client():
    path = os.path.join(STATIC_DIR, "client.html")
    return HTMLResponse(open(path).read()) if os.path.exists(path) else HTMLResponse("Not found", 404)

# --- Auth ──────────────────────────────────────────────────────────────────────
@app.post("/auth/admin/login")
def login_admin(data: LoginRequest): return admin_login(data.email, data.password)

@app.post("/auth/client/login")
def login_client(data: LoginRequest): return client_login(data.email, data.password)

# --- Visa Requirements (Public) ────────────────────────────────────────────────
@app.get("/api/countries")
def get_countries():
    from visa_requirements import get_country_list
    return {"countries": get_country_list()}

@app.get("/api/country/{country_code}")
def get_country_details(country_code: str):
    from visa_requirements import get_country_info
    info = get_country_info(country_code.upper())
    if not info: raise HTTPException(404, "Country not found")
    return info

@app.get("/api/visa-requirements/{country}/{visa_type}")
def get_visa_requirements(country: str, visa_type: str):
    from visa_requirements import format_visa_details, get_document_checklist
    return {
        "details": format_visa_details(country.upper(), visa_type.lower()),
        "checklist": get_document_checklist(country.upper(), visa_type.lower()),
    }

@app.post("/api/search-countries")
def search_countries_api(data: CountrySearch):
    from visa_requirements import search_countries
    return {"results": search_countries(data.query)}

# --- Admin Dashboard ───────────────────────────────────────────────────────────
@app.get("/admin/dashboard")
def admin_dashboard(admin=Depends(require_admin)):
    conn = get_db()
    apps = conn.execute("""
        SELECT a.*, c.name as client_name, c.email as client_email, c.phone as client_phone
        FROM applications a JOIN clients c ON c.id=a.client_id
        ORDER BY a.created_at DESC
    """).fetchall()
    stats = {
        "total":    conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0],
        "pending":  conn.execute("SELECT COUNT(*) FROM applications WHERE status='pending'").fetchone()[0],
        "review":   conn.execute("SELECT COUNT(*) FROM applications WHERE status='review'").fetchone()[0],
        "approved": conn.execute("SELECT COUNT(*) FROM applications WHERE status='approved'").fetchone()[0],
        "rejected": conn.execute("SELECT COUNT(*) FROM applications WHERE status='rejected'").fetchone()[0],
        "clients":  conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0],
        "this_month": conn.execute(
            "SELECT COUNT(*) FROM applications WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"
        ).fetchone()[0],
        "this_year": conn.execute(
            "SELECT COUNT(*) FROM applications WHERE strftime('%Y', created_at) = strftime('%Y', 'now')"
        ).fetchone()[0],
    }
    conn.close()
    return {"stats": stats, "applications": [dict(a) for a in apps]}

@app.get("/admin/application/{app_id}")
def admin_get_application(app_id: str, admin=Depends(require_admin)):
    conn = get_db()
    app = conn.execute("""
        SELECT a.*, c.name as client_name, c.email as client_email, c.phone as client_phone
        FROM applications a JOIN clients c ON c.id=a.client_id WHERE a.app_id=?
    """, (app_id,)).fetchone()
    if not app: conn.close(); raise HTTPException(404, "Not found")
    docs = conn.execute("SELECT * FROM documents WHERE app_id=?", (app_id,)).fetchall()
    logs = conn.execute("SELECT * FROM activity_log WHERE app_id=? ORDER BY created_at DESC", (app_id,)).fetchall()
    cl   = conn.execute("SELECT * FROM custom_checklists WHERE id=?", (app["checklist_id"],)).fetchone() if app["checklist_id"] else None
    comm = conn.execute("SELECT * FROM communication_log WHERE app_id=? ORDER BY created_at DESC", (app_id,)).fetchall()
    conn.close()
    return {
        "application": dict(app),
        "documents":   [dict(d) for d in docs],
        "activity":    [dict(l) for l in logs],
        "checklist":   dict(cl) if cl else None,
        "comm_log":    [dict(c) for c in comm],
    }

@app.post("/admin/application/{app_id}/status")
def admin_update_status(app_id: str, data: UpdateStatusRequest, admin=Depends(require_roles("visa_staff"))):
    if data.status not in STATUS_PROGRESS: raise HTTPException(400, "Invalid status")
    conn = get_db()
    app = conn.execute("SELECT * FROM applications WHERE app_id=?", (app_id,)).fetchone()
    if not app: conn.close(); raise HTTPException(404, "Not found")
    client = conn.execute("SELECT * FROM clients WHERE id=?", (app["client_id"],)).fetchone()
    old_status = app["status"]
    conn.execute("UPDATE applications SET status=?, progress=?, updated_at=CURRENT_TIMESTAMP WHERE app_id=?",
                 (data.status, STATUS_PROGRESS[data.status], app_id))
    conn.execute("INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
                 (app_id, f"admin:{admin['name']}", "Status updated", f"{old_status} → {data.status}. {data.note}"))
    conn.execute("INSERT INTO notifications (client_id, app_id, message) VALUES (?,?,?)",
                 (client["id"], app_id, f"Your application {app_id} updated to: {data.status}."))
    conn.commit(); conn.close()
    send_status_update(client["name"], client["phone"] or "", client["email"],
                       app_id, data.status, data.note or "", data.channels or ["whatsapp","email"])
    return {"status": "updated", "new_status": data.status}

@app.post("/admin/clients")
def admin_create_client(data: NewClientRequest, admin=Depends(require_admin)):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO clients (name, email, phone, password, passport_b64, passport_filename) VALUES (?,?,?,?,?,?)",
            (data.name, data.email, data.phone, hash_password(data.password),
             data.passport_b64, data.passport_filename)
        )
        conn.commit(); conn.close()
        return {"status": "created"}
    except Exception as e:
        conn.close(); raise HTTPException(400, str(e))

@app.get("/admin/client/{client_id}/passport")
def admin_get_passport(client_id: int, admin=Depends(require_admin)):
    """Return passport as base64 so admin can view/download it."""
    conn = get_db()
    row = conn.execute(
        "SELECT name, passport_b64, passport_filename FROM clients WHERE id=?", (client_id,)
    ).fetchone()
    conn.close()
    if not row or not row["passport_b64"]:
        raise HTTPException(404, "No passport on file for this client")
    return {
        "client_name":       row["name"],
        "passport_b64":      row["passport_b64"],
        "passport_filename": row["passport_filename"] or "passport.jpg",
    }

@app.post("/admin/application/{app_id}/team-note")
def admin_add_team_note(app_id: str, data: dict, admin=Depends(require_admin)):
    """Save an internal team note — not visible to clients."""
    note = data.get("note", "").strip()
    if not note:
        raise HTTPException(400, "Note cannot be empty")
    conn = get_db()
    conn.execute(
        "INSERT INTO team_notes (app_id, author, note) VALUES (?,?,?)",
        (app_id, admin["name"], note)
    )
    conn.execute(
        "INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
        (app_id, f"staff:{admin['name']}", "Team note added", note[:80])
    )
    conn.commit(); conn.close()
    return {"status": "saved"}

@app.get("/admin/application/{app_id}/team-notes")
def admin_get_team_notes(app_id: str, admin=Depends(require_admin)):
    conn = get_db()
    notes = conn.execute(
        "SELECT * FROM team_notes WHERE app_id=? ORDER BY created_at DESC", (app_id,)
    ).fetchall()
    conn.close()
    return {"notes": [dict(n) for n in notes]}

@app.post("/admin/application")
def admin_create_application(data: NewApplicationRequest, admin=Depends(require_roles("visa_staff"))):
    conn = get_db()
    client = conn.execute("SELECT * FROM clients WHERE email=?", (data.client_email,)).fetchone()

    # Auto-create a minimal client record if one doesn't exist yet
    if not client:
        name  = data.client_name or data.client_email.split("@")[0].replace(".", " ").title()
        phone = data.client_phone or ""
        # Generate a random temporary password they can reset later
        import secrets
        tmp_pw = secrets.token_hex(6)
        from auth import hash_password as _hp
        conn.execute(
            "INSERT INTO clients (name, email, phone, password) VALUES (?,?,?,?)",
            (name, data.client_email, phone, _hp(tmp_pw))
        )
        conn.commit()
        client = conn.execute("SELECT * FROM clients WHERE email=?", (data.client_email,)).fetchone()

    count  = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    app_id = f"VIS-{now_ist().year}-{str(count+1).zfill(3)}"
    conn.execute("INSERT INTO applications (app_id, client_id, destination, visa_type, travel_date, checklist_id) VALUES (?,?,?,?,?,?)",
                 (app_id, client["id"], data.destination, data.visa_type, data.travel_date, data.checklist_id))
    doc_map = {
        "tourist":  ["passport","photo","bank_statement","hotel_booking","flight_ticket","travel_insurance"],
        "business": ["passport","photo","bank_statement","invitation_letter","flight_ticket","company_letter"],
        "student":  ["passport","photo","bank_statement","admission_letter","flight_ticket","accommodation_proof"],
        "transit":  ["passport","photo","onward_ticket"],
    }
    for dt in doc_map.get(data.visa_type, ["passport","photo","bank_statement"]):
        conn.execute("INSERT INTO documents (app_id, doc_type, status) VALUES (?,?,?)", (app_id, dt, "missing"))
    conn.execute("INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
                 (app_id, f"admin:{admin['name']}", "Application created", f"{data.visa_type} for {data.destination}"))
    conn.commit()
    checklist_docs = []
    if data.checklist_id:
        cl = conn.execute("SELECT * FROM custom_checklists WHERE id=?", (data.checklist_id,)).fetchone()
        if cl: checklist_docs = json.loads(cl["documents_json"])
    conn.close()
    send_checklist(client["name"], client["phone"] or "", client["email"], app_id,
                   data.destination, data.visa_type,
                   checklist_docs or doc_map.get(data.visa_type, []),
                   channels=["whatsapp", "email"])
    return {"status": "created", "app_id": app_id, "client_name": client["name"]}

@app.post("/admin/application/{app_id}/verify-doc")
def admin_verify_doc(app_id: str, data: UpdateDocStatusRequest, admin=Depends(require_roles("visa_staff"))):
    conn = get_db()
    conn.execute("UPDATE documents SET status=?, notes=?, verified_at=CURRENT_TIMESTAMP WHERE id=?",
                 (data.status, data.notes, data.doc_id))
    conn.execute("INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
                 (app_id, f"admin:{admin['name']}", "Document verified", f"Doc {data.doc_id} → {data.status}"))
    conn.commit(); conn.close()
    return {"status": "updated"}

# --- Checklists & Pricing ──────────────────────────────────────────────────────
@app.post("/admin/checklist/create")
def create_checklist(data: CustomChecklistData, admin=Depends(require_roles("visa_staff"))):
    # Service charge is ADDITIVE — final = base + base*(pct/100)
    final_price = data.base_price * (1 + data.discount_percentage / 100)
    conn = get_db()
    try:
        conn.execute("""INSERT INTO custom_checklists
            (country, visa_type, name, description, documents_json, base_price, discount_percentage, final_price, created_by)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (data.country, data.visa_type, data.name, data.description,
             json.dumps(data.documents), data.base_price, data.discount_percentage, final_price, admin["name"]))
        conn.commit()
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return {"status": "success", "id": new_id}
    except Exception as e:
        conn.close(); raise HTTPException(400, str(e))


@app.get("/admin/checklist/{checklist_id}")
def get_checklist(checklist_id: int, admin=Depends(require_admin)):
    conn = get_db()
    row = conn.execute("SELECT * FROM custom_checklists WHERE id=?", (checklist_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Checklist not found")
    d = dict(row)
    d["documents"] = json.loads(d["documents_json"])
    return {"checklist": d}

@app.get("/admin/checklists")
def get_all_checklists(admin=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM custom_checklists ORDER BY created_at DESC").fetchall()
    conn.close()
    result = [dict(r) | {"documents": json.loads(r["documents_json"])} for r in rows]
    return {"checklists": result}

@app.get("/admin/checklists/{country}")
def get_checklists_by_country(country: str, admin=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM custom_checklists WHERE LOWER(country)=LOWER(?) ORDER BY created_at DESC", (country,)).fetchall()
    conn.close()
    result = [dict(r) | {"documents": json.loads(r["documents_json"])} for r in rows]
    return {"checklists": result}

@app.put("/admin/checklist/{checklist_id}")
def update_checklist(checklist_id: int, data: UpdateChecklistData, admin=Depends(require_roles("visa_staff"))):
    """
    Note: field name 'discount_percentage' is kept for DB compatibility, but
    it represents an ADDITIVE service charge percentage, not a price reduction
    (consistent with fee structure and invoice service charges elsewhere).
    """
    conn = get_db()
    if data.base_price is not None:
        conn.execute("UPDATE custom_checklists SET base_price=? WHERE id=?", (data.base_price, checklist_id))
    if data.discount_percentage is not None:
        row = conn.execute("SELECT base_price FROM custom_checklists WHERE id=?", (checklist_id,)).fetchone()
        fp = (row["base_price"] if row else 0) * (1 + data.discount_percentage/100)
        conn.execute("UPDATE custom_checklists SET discount_percentage=?, final_price=? WHERE id=?", (data.discount_percentage, fp, checklist_id))
    if data.documents is not None:
        conn.execute("UPDATE custom_checklists SET documents_json=? WHERE id=?", (json.dumps(data.documents), checklist_id))
    conn.execute("UPDATE custom_checklists SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (checklist_id,))
    conn.commit(); conn.close()
    return {"status": "updated"}

@app.delete("/admin/checklist/{checklist_id}")
def delete_checklist(checklist_id: int, admin=Depends(require_roles("visa_staff"))):
    conn = get_db()
    row = conn.execute("SELECT id FROM custom_checklists WHERE id=?", (checklist_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Checklist not found")
    conn.execute("DELETE FROM custom_checklists WHERE id=?", (checklist_id,))
    conn.commit(); conn.close()
    return {"status": "deleted"}

@app.post("/admin/checklists/export-pdf")
def export_checklists_pdf(data: ExportChecklistsRequest, admin=Depends(require_admin)):
    """
    Generate a single PDF containing one formatted page per selected
    checklist, in the standard VFS-style layout: header block (country,
    visa type, service charge) followed by a numbered document list.
    """
    if not data.checklist_ids:
        raise HTTPException(400, "Select at least one checklist to export")

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    conn = get_db()
    placeholders = ",".join("?" * len(data.checklist_ids))
    rows = conn.execute(
        f"SELECT * FROM custom_checklists WHERE id IN ({placeholders}) ORDER BY country, visa_type",
        data.checklist_ids
    ).fetchall()
    conn.close()

    if not rows:
        raise HTTPException(404, "No matching checklists found")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(
        tmp.name, pagesize=A4,
        topMargin=20*mm, bottomMargin=20*mm, leftMargin=20*mm, rightMargin=20*mm
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ChecklistTitle", parent=styles["Title"], fontSize=16,
        textColor=colors.HexColor("#1e3a5f"), alignment=TA_CENTER, spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        "ChecklistSubtitle", parent=styles["Normal"], fontSize=10,
        textColor=colors.HexColor("#666666"), alignment=TA_CENTER, spaceAfter=16
    )
    section_style = ParagraphStyle(
        "SectionHeader", parent=styles["Heading2"], fontSize=12,
        textColor=colors.HexColor("#1e3a5f"), spaceBefore=10, spaceAfter=8
    )
    doc_item_style = ParagraphStyle(
        "DocItem", parent=styles["Normal"], fontSize=10.5, leading=16, spaceAfter=4
    )
    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"], fontSize=8,
        textColor=colors.HexColor("#888888"), spaceBefore=20
    )

    story = []
    for i, row in enumerate(rows):
        cl = dict(row)
        documents = json.loads(cl["documents_json"])

        story.append(Paragraph("UNIGLOBE MKOV TRAVEL", title_style))
        story.append(Paragraph("Visa Document Checklist", subtitle_style))

        # Header info block — name/passport/email/mobile fields for the applicant to fill in
        header_data = [
            ["Country:", cl["country"], "Visa Type:", cl["visa_type"].title()],
            ["Applicant Name:", "_" * 28, "Passport No.:", "_" * 20],
            ["Email ID:", "_" * 28, "Mobile No.:", "_" * 20],
        ]
        header_table = Table(header_data, colWidths=[28*mm, 62*mm, 28*mm, 52*mm])
        header_table.setStyle(TableStyle([
            ("FONTSIZE", (0,0), (-1,-1), 9.5),
            ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
            ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("LINEBELOW", (0,0), (-1,-1), 0.5, colors.HexColor("#dddddd")),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 14))

        if cl.get("final_price"):
            story.append(Paragraph(f"Service Charge: Rs. {cl['final_price']:.2f}", section_style))

        story.append(Paragraph("Required Documents", section_style))
        for idx, item in enumerate(documents, 1):
            story.append(Paragraph(f"{idx}. [ ] {item}", doc_item_style))

        story.append(Paragraph(
            "Please ensure all documents are originals or self-attested photocopies as applicable. "
            "Incomplete submissions may delay processing.",
            footer_style
        ))
        story.append(Paragraph(
            "Applicant Signature: ______________________     Date: ______________",
            footer_style
        ))

        if i < len(rows) - 1:
            story.append(PageBreak())

    doc.build(story)

    filename = "vfs_checklist_export.pdf" if len(rows) > 1 else f"{rows[0]['country']}_{rows[0]['visa_type']}_checklist.pdf"
    return FileResponse(tmp.name, filename=filename, media_type="application/pdf")


def add_client_discount(data: ClientDiscountData, admin=Depends(require_roles("visa_staff"))):
    conn = get_db()
    try:
        conn.execute("INSERT INTO client_discounts (client_id, checklist_id, discount_type, discount_value, reason, created_by) VALUES (?,?,?,?,?,?)",
                     (data.client_id, data.checklist_id, data.discount_type, data.discount_value, data.reason, admin["name"]))
        conn.commit(); conn.close()
        return {"status": "success"}
    except Exception as e:
        conn.close(); raise HTTPException(400, str(e))

@app.get("/admin/client-discounts/{client_id}")
def get_client_discounts(client_id: int, admin=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM client_discounts WHERE client_id=? AND active=1", (client_id,)).fetchall()
    conn.close()
    return {"discounts": [dict(r) for r in rows]}

# --- Multi-Channel Send ────────────────────────────────────────────────────────
@app.post("/admin/send-checklist")
def admin_send_checklist(data: SendChecklistRequest, admin=Depends(require_admin)):
    conn = get_db()
    app = conn.execute("""SELECT a.*, c.name as client_name, c.email as client_email, c.phone as client_phone
        FROM applications a JOIN clients c ON c.id=a.client_id WHERE a.app_id=?""", (data.app_id,)).fetchone()
    if not app: conn.close(); raise HTTPException(404, "Application not found")
    docs, price = [], 0
    if app["checklist_id"]:
        cl = conn.execute("SELECT * FROM custom_checklists WHERE id=?", (app["checklist_id"],)).fetchone()
        if cl: docs = json.loads(cl["documents_json"]); price = cl["final_price"]
    if not docs:
        doc_map = {
            "tourist":  ["Passport","Photo","Bank Statement","Hotel Booking","Return Flight","Travel Insurance"],
            "business": ["Passport","Photo","Bank Statement","Invitation Letter","Return Flight","Company Letter"],
            "student":  ["Passport","Photo","Bank Statement","Admission Letter","Return Flight","Accommodation Proof"],
        }
        docs = doc_map.get(app["visa_type"], ["Passport","Photo","Bank Statement"])
    conn.close()
    send_checklist(app["client_name"], app["client_phone"] or "", app["client_email"],
                   data.app_id, app["destination"], app["visa_type"], docs, price, data.channels)
    return {"status": "success", "sent_via": data.channels}

@app.post("/admin/send-status-update")
def admin_send_status(data: SendStatusRequest, admin=Depends(require_admin)):
    conn = get_db()
    app = conn.execute("""SELECT a.*, c.name as client_name, c.email as client_email, c.phone as client_phone
        FROM applications a JOIN clients c ON c.id=a.client_id WHERE a.app_id=?""", (data.app_id,)).fetchone()
    if not app: conn.close(); raise HTTPException(404, "Not found")
    if data.new_status in STATUS_PROGRESS:
        conn.execute("UPDATE applications SET status=?, progress=?, updated_at=CURRENT_TIMESTAMP WHERE app_id=?",
                     (data.new_status, STATUS_PROGRESS[data.new_status], data.app_id))
        conn.execute("INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
                     (data.app_id, f"admin:{admin['name']}", "Status updated", f"{app['status']} → {data.new_status}"))
        conn.commit()
    conn.close()
    send_status_update(app["client_name"], app["client_phone"] or "", app["client_email"],
                       data.app_id, data.new_status, data.note or "", data.channels)
    return {"status": "sent", "sent_via": data.channels}

@app.post("/admin/send-reminder")
def admin_send_reminder(data: SendReminderRequest, admin=Depends(require_admin)):
    conn = get_db()
    app = conn.execute("""SELECT a.*, c.name as client_name, c.email as client_email, c.phone as client_phone
        FROM applications a JOIN clients c ON c.id=a.client_id WHERE a.app_id=?""", (data.app_id,)).fetchone()
    if not app: conn.close(); raise HTTPException(404, "Not found")
    conn.close()
    send_reminder(app["client_name"], app["client_phone"] or "", app["client_email"],
                  data.app_id, data.missing_docs, data.channels)
    return {"status": "sent", "sent_via": data.channels}

@app.get("/admin/communication-log/{app_id}")
def get_communication_log(app_id: str, admin=Depends(require_admin)):
    conn = get_db()
    logs = conn.execute("SELECT * FROM communication_log WHERE app_id=? ORDER BY created_at DESC", (app_id,)).fetchall()
    conn.close()
    return {"logs": [dict(l) for l in logs]}

@app.get("/admin/communication-log")
def get_all_communication_logs(admin=Depends(require_admin)):
    """Global communication log across all clients/applications, for export."""
    conn = get_db()
    rows = conn.execute("""
        SELECT cl.*, c.name as client_name, c.email as client_email
        FROM communication_log cl
        LEFT JOIN clients c ON c.id = cl.client_id
        ORDER BY cl.created_at DESC
    """).fetchall()
    conn.close()
    return {"logs": [dict(r) for r in rows]}

@app.get("/admin/webhook-log")
def admin_webhook_log(admin=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM webhook_log ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- Client Routes ─────────────────────────────────────────────────────────────
@app.get("/client/dashboard")
def client_dashboard(client=Depends(require_client)):
    conn = get_db()
    client_row = conn.execute("SELECT * FROM clients WHERE email=?", (client["sub"],)).fetchone()
    if not client_row: conn.close(); raise HTTPException(404, "Client not found")
    apps  = conn.execute("SELECT * FROM applications WHERE client_id=? ORDER BY created_at DESC", (client_row["id"],)).fetchall()
    notifs = conn.execute("SELECT * FROM notifications WHERE client_id=? ORDER BY created_at DESC LIMIT 10", (client_row["id"],)).fetchall()
    conn.close()
    return {"client": dict(client_row), "applications": [dict(a) for a in apps],
            "notifications": [dict(n) for n in notifs], "unread_count": sum(1 for n in notifs if not n["read"])}

@app.get("/client/application/{app_id}")
def client_get_application(app_id: str, client=Depends(require_client)):
    conn = get_db()
    client_row = conn.execute("SELECT * FROM clients WHERE email=?", (client["sub"],)).fetchone()
    app = conn.execute("SELECT * FROM applications WHERE app_id=? AND client_id=?", (app_id, client_row["id"])).fetchone()
    if not app: conn.close(); raise HTTPException(404, "Application not found")
    docs = conn.execute("SELECT * FROM documents WHERE app_id=?", (app_id,)).fetchall()
    logs = conn.execute("SELECT * FROM activity_log WHERE app_id=? ORDER BY created_at DESC", (app_id,)).fetchall()
    checklist = None
    if app["checklist_id"]:
        cl = conn.execute("SELECT * FROM custom_checklists WHERE id=?", (app["checklist_id"],)).fetchone()
        if cl: checklist = dict(cl) | {"documents": json.loads(cl["documents_json"])}
    conn.close()
    return {"application": dict(app), "documents": [dict(d) for d in docs],
            "activity": [dict(l) for l in logs], "checklist": checklist}

@app.get("/client/download-checklist/{app_id}")
def client_download_checklist(app_id: str, client=Depends(require_client)):
    conn = get_db()
    client_row = conn.execute("SELECT * FROM clients WHERE email=?", (client["sub"],)).fetchone()
    app = conn.execute("SELECT * FROM applications WHERE app_id=? AND client_id=?", (app_id, client_row["id"])).fetchone()
    if not app: conn.close(); raise HTTPException(404, "Not found")
    documents, final_price = [], 0
    if app["checklist_id"]:
        cl = conn.execute("SELECT * FROM custom_checklists WHERE id=?", (app["checklist_id"],)).fetchone()
        if cl: documents = json.loads(cl["documents_json"]); final_price = cl["final_price"]
    if not documents:
        docs = conn.execute("SELECT doc_type FROM documents WHERE app_id=?", (app_id,)).fetchall()
        documents = [d["doc_type"].replace("_"," ").title() for d in docs]
    conn.close()
    text = f"""╔════════════════════════════════════════════╗
║         VISA APPLICATION CHECKLIST
╚════════════════════════════════════════════╝

Application ID:  {app_id}
Destination:     {app['destination']}
Visa Type:       {app['visa_type'].title()}
Status:          {app['status'].title()}

REQUIRED DOCUMENTS:
"""
    for i, doc in enumerate(documents, 1):
        text += f"  {i}. [ ] {doc}\n"
    if final_price:
        text += f"\nSERVICE CHARGE: ₹{final_price:.2f}\n"
    text += f"\nUpload at: https://arya-v1-0-0.onrender.com/client\nHelp: +91-8010700700\n"
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    tmp.write(text); tmp.flush()
    return FileResponse(tmp.name, filename=f"{app_id}_checklist.txt", media_type="text/plain")

@app.post("/client/application/{app_id}/upload")
async def client_upload_doc(app_id: str, doc_type: str = Form(...), file: UploadFile = File(...), client=Depends(require_client)):
    conn = get_db()
    client_row = conn.execute("SELECT * FROM clients WHERE email=?", (client["sub"],)).fetchone()
    app = conn.execute("SELECT * FROM applications WHERE app_id=? AND client_id=?", (app_id, client_row["id"])).fetchone()
    if not app: conn.close(); raise HTTPException(404, "Not found")
    ext = os.path.splitext(file.filename)[1]
    file_name = f"{app_id}_{doc_type}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    now = now_ist_str()
    conn.execute("UPDATE documents SET status='uploaded', file_name=?, file_path=?, uploaded_at=? WHERE app_id=? AND doc_type=?",
                 (file_name, file_path, now, app_id, doc_type))
    conn.execute("INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
                 (app_id, f"client:{client_row['name']}", "Document uploaded", f"Uploaded {doc_type}: {file_name}"))
    conn.commit(); conn.close()
    return {"status": "uploaded", "file_name": file_name, "doc_type": doc_type}

@app.get("/client/document/{app_id}/{doc_type}")
def client_get_document(app_id: str, doc_type: str, client=Depends(require_client)):
    conn = get_db()
    client_row = conn.execute("SELECT * FROM clients WHERE email=?", (client["sub"],)).fetchone()
    app = conn.execute("SELECT * FROM applications WHERE app_id=? AND client_id=?", (app_id, client_row["id"])).fetchone()
    if not app: conn.close(); raise HTTPException(403, "Not authorised")
    doc = conn.execute("SELECT * FROM documents WHERE app_id=? AND doc_type=?", (app_id, doc_type)).fetchone()
    conn.close()
    if not doc or not doc["file_path"]: raise HTTPException(404, "Document not uploaded yet")
    if not os.path.exists(doc["file_path"]): raise HTTPException(404, "File not found")
    return FileResponse(doc["file_path"], filename=doc["file_name"])

@app.post("/client/notifications/read-all")
def client_mark_read(client=Depends(require_client)):
    conn = get_db()
    client_row = conn.execute("SELECT id FROM clients WHERE email=?", (client["sub"],)).fetchone()
    conn.execute("UPDATE notifications SET read=1 WHERE client_id=?", (client_row["id"],))
    conn.commit(); conn.close()
    return {"status": "all marked read"}


# ══════════════════════════════════════════════════════════════════════════════
# NEW ENDPOINTS — Client Management, Fee Structure, Document Upload
# ══════════════════════════════════════════════════════════════════════════════

class UpdateClientRequest(BaseModel):
    name:     Optional[str] = None
    phone:    Optional[str] = None
    email:    Optional[str] = None
    password: Optional[str] = None

class FeeStructureRequest(BaseModel):
    client_id:       int
    label:           str            # "USA Tourist Standard"
    base_price:      float
    discount_type:   str            # "percentage" | "fixed" | "none"
    discount_value:  float = 0
    reason:          Optional[str] = ""   # "Frequent flyer", "Referral"
    app_id:          Optional[str] = None # tie to specific application

class UpdateApplicationRequest(BaseModel):
    destination:   Optional[str] = None
    visa_type:     Optional[str] = None
    travel_date:   Optional[str] = None
    duration_days: Optional[int] = None
    group_size:    Optional[int] = None
    embassy_ref:   Optional[str] = None
    notes:         Optional[str] = None
    checklist_id:  Optional[int] = None


# ── GET all clients (proper endpoint) ────────────────────────────────────────
@app.get("/admin/clients")
def admin_get_clients(admin=Depends(require_admin)):
    """Get all clients with their application counts."""
    conn = get_db()
    rows = conn.execute("""
        SELECT c.id, c.name, c.email, c.phone, c.created_at,
               c.passport_filename,
               COUNT(a.id) as app_count,
               MAX(a.created_at) as last_app
        FROM clients c
        LEFT JOIN applications a ON a.client_id = c.id
        GROUP BY c.id
        ORDER BY c.created_at DESC
    """).fetchall()
    conn.close()
    return {"clients": [dict(r) for r in rows]}


# ── GET single client with full details ───────────────────────────────────────
@app.get("/admin/client/{client_id}")
def admin_get_client(client_id: int, admin=Depends(require_admin)):
    """Get full client profile with applications, discounts, documents."""
    conn = get_db()
    client = conn.execute(
        "SELECT id, name, email, phone, created_at, passport_filename FROM clients WHERE id=?",
        (client_id,)
    ).fetchone()
    if not client:
        conn.close()
        raise HTTPException(404, "Client not found")

    apps = conn.execute(
        "SELECT * FROM applications WHERE client_id=? ORDER BY created_at DESC",
        (client_id,)
    ).fetchall()

    discounts = conn.execute(
        "SELECT * FROM client_discounts WHERE client_id=? AND active=1 ORDER BY created_at DESC",
        (client_id,)
    ).fetchall()

    docs = conn.execute("""
        SELECT d.*, a.destination, a.visa_type
        FROM documents d
        JOIN applications a ON a.app_id = d.app_id
        WHERE a.client_id = ?
        ORDER BY d.uploaded_at DESC
    """, (client_id,)).fetchall()

    conn.close()
    return {
        "client":    dict(client),
        "applications": [dict(a) for a in apps],
        "discounts": [dict(d) for d in discounts],
        "documents": [dict(d) for d in docs],
    }


# ── UPDATE client details ─────────────────────────────────────────────────────
@app.put("/admin/client/{client_id}")
def admin_update_client(client_id: int, data: UpdateClientRequest, admin=Depends(require_admin)):
    """Edit client name, phone, email, or reset password."""
    conn = get_db()
    client = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if not client:
        conn.close()
        raise HTTPException(404, "Client not found")

    updates = []
    values  = []
    if data.name:
        updates.append("name=?");     values.append(data.name)
    if data.phone:
        updates.append("phone=?");    values.append(data.phone)
    if data.email:
        updates.append("email=?");    values.append(data.email)
    if data.password:
        updates.append("password=?"); values.append(hash_password(data.password))

    if updates:
        values.append(client_id)
        conn.execute(f"UPDATE clients SET {', '.join(updates)} WHERE id=?", values)
        conn.commit()

    conn.close()
    return {"status": "updated"}


# ── UPLOAD client passport (base64) ──────────────────────────────────────────
@app.post("/admin/client/{client_id}/upload-passport")
async def admin_upload_passport(
    client_id: int,
    file: UploadFile = File(...),
    admin=Depends(require_admin)
):
    """Upload passport scan and store as base64 in DB."""
    conn = get_db()
    client = conn.execute("SELECT id FROM clients WHERE id=?", (client_id,)).fetchone()
    if not client:
        conn.close()
        raise HTTPException(404, "Client not found")

    # Read file and encode as base64
    import base64
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:   # 10MB limit
        conn.close()
        raise HTTPException(400, "File too large (max 10MB)")

    b64 = base64.b64encode(content).decode()
    conn.execute(
        "UPDATE clients SET passport_b64=?, passport_filename=? WHERE id=?",
        (b64, file.filename, client_id)
    )
    conn.commit()
    conn.close()
    return {"status": "uploaded", "filename": file.filename}


# ── UPLOAD document for specific application ──────────────────────────────────
@app.post("/admin/application/{app_id}/upload-doc")
async def admin_upload_doc(
    app_id:   str,
    doc_type: str = Form(...),
    file:     UploadFile = File(...),
    admin=Depends(require_admin)
):
    """Admin uploads a document for a client (e.g. approved visa copy)."""
    import base64
    conn = get_db()
    app = conn.execute("SELECT * FROM applications WHERE app_id=?", (app_id,)).fetchone()
    if not app:
        conn.close()
        raise HTTPException(404, "Application not found")

    content = await file.read()
    b64     = base64.b64encode(content).decode()
    now     = now_ist_str()

    # Check if doc_type row exists — update or insert
    existing = conn.execute(
        "SELECT id FROM documents WHERE app_id=? AND doc_type=?", (app_id, doc_type)
    ).fetchone()

    if existing:
        conn.execute("""
            UPDATE documents
            SET file_name=?, file_path=?, status='uploaded', uploaded_at=?
            WHERE app_id=? AND doc_type=?
        """, (file.filename, b64, now, app_id, doc_type))
    else:
        conn.execute("""
            INSERT INTO documents (app_id, doc_type, file_name, file_path, status, uploaded_at)
            VALUES (?,?,?,?,?,?)
        """, (app_id, doc_type, file.filename, b64, "uploaded", now))

    conn.execute(
        "INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
        (app_id, f"admin:{admin['name']}", "Document uploaded",
         f"Admin uploaded {doc_type}: {file.filename}")
    )
    conn.commit()
    conn.close()
    return {"status": "uploaded", "doc_type": doc_type, "filename": file.filename}


# ── GET document as base64 (admin) ───────────────────────────────────────────
@app.get("/admin/document/{doc_id}")
def admin_get_document(doc_id: int, admin=Depends(require_admin)):
    """Return document as base64 for viewing in browser."""
    conn = get_db()
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    conn.close()
    if not doc:
        raise HTTPException(404, "Document not found")
    if not doc["file_path"]:
        raise HTTPException(404, "No file uploaded for this document")
    return {
        "doc_type":  doc["doc_type"],
        "file_name": doc["file_name"],
        "file_b64":  doc["file_path"],  # stored as b64 in file_path column
        "status":    doc["status"],
    }


# ── UPDATE application details ────────────────────────────────────────────────
@app.put("/admin/application/{app_id}")
def admin_update_application(app_id: str, data: UpdateApplicationRequest, admin=Depends(require_roles("visa_staff"))):
    """Edit destination, dates, notes, embassy ref etc."""
    conn = get_db()
    app = conn.execute("SELECT * FROM applications WHERE app_id=?", (app_id,)).fetchone()
    if not app:
        conn.close()
        raise HTTPException(404, "Application not found")

    updates = ["updated_at=CURRENT_TIMESTAMP"]
    values  = []
    fields  = {
        "destination":   data.destination,
        "visa_type":     data.visa_type,
        "travel_date":   data.travel_date,
        "duration_days": data.duration_days,
        "group_size":    data.group_size,
        "embassy_ref":   data.embassy_ref,
        "notes":         data.notes,
        "checklist_id":  data.checklist_id,
    }
    for col, val in fields.items():
        if val is not None:
            updates.append(f"{col}=?")
            values.append(val)

    if len(updates) > 1:
        values.append(app_id)
        conn.execute(f"UPDATE applications SET {', '.join(updates)} WHERE app_id=?", values)
        conn.execute(
            "INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
            (app_id, f"admin:{admin['name']}", "Application updated",
             f"Fields updated: {', '.join(k for k,v in fields.items() if v is not None)}")
        )
        conn.commit()

    conn.close()
    return {"status": "updated"}


# ── SET fee structure for client ──────────────────────────────────────────────
@app.post("/admin/client-fee")
def admin_set_client_fee(data: FeeStructureRequest, admin=Depends(require_roles("visa_staff"))):
    """
    Set a custom service charge for a specific client.
    discount_type: 'percentage' = e.g. 10% added on top of base price
                   'fixed'      = e.g. INR 500 added on top of base price
                   'none'       = base price only, no extra charge
    Note: field names (discount_type/discount_value/client_discounts table) are
    kept for DB compatibility, but the value is now ADDED to the base price as
    a service charge, not subtracted as a discount.
    """
    conn = get_db()
    client = conn.execute("SELECT id, name FROM clients WHERE id=?", (data.client_id,)).fetchone()
    if not client:
        conn.close()
        raise HTTPException(404, "Client not found")

    # Calculate final price — service charge is ADDED to base price
    if data.discount_type == "percentage":
        final = data.base_price * (1 + data.discount_value / 100)
    elif data.discount_type == "fixed":
        final = data.base_price + data.discount_value
    else:
        final = data.base_price

    conn.execute("""
        INSERT INTO client_discounts
        (client_id, checklist_id, discount_type, discount_value, reason, created_by)
        VALUES (?,?,?,?,?,?)
    """, (
        data.client_id,
        None,
        data.discount_type,
        data.discount_value,
        f"{data.label} | Base: {data.base_price} | Final: {final} | {data.reason}",
        admin["name"]
    ))

    # If tied to an application, log it
    if data.app_id:
        conn.execute(
            "INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
            (data.app_id, f"admin:{admin['name']}", "Service charge updated",
             f"{data.label}: ₹{data.base_price} → ₹{final:.0f} ({data.discount_type}: {data.discount_value})")
        )

    conn.commit()
    conn.close()
    return {
        "status":      "set",
        "base_price":  data.base_price,
        "final_price": final,
        "client_name": client["name"]
    }


# ── GET fee structure for client ──────────────────────────────────────────────
@app.get("/admin/client-fee/{client_id}")
def admin_get_client_fee(client_id: int, admin=Depends(require_admin)):
    """Get all fee entries for a client."""
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM client_discounts
        WHERE client_id=? AND active=1
        ORDER BY created_at DESC
    """, (client_id,)).fetchall()
    conn.close()
    return {"fees": [dict(r) for r in rows]}


# ── DELETE (deactivate) a fee entry ──────────────────────────────────────────
@app.delete("/admin/client-fee/{fee_id}")
def admin_delete_client_fee(fee_id: int, admin=Depends(require_roles("visa_staff"))):
    conn = get_db()
    conn.execute("UPDATE client_discounts SET active=0 WHERE id=?", (fee_id,))
    conn.commit()
    conn.close()
    return {"status": "removed"}


# ── Add document type to an application checklist ────────────────────────────
@app.post("/admin/application/{app_id}/add-doc-type")
def admin_add_doc_type(app_id: str, data: dict, admin=Depends(require_roles("visa_staff"))):
    """Add a new document slot to an application."""
    doc_type = data.get("doc_type", "").strip().lower().replace(" ", "_")
    if not doc_type:
        raise HTTPException(400, "doc_type required")
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM documents WHERE app_id=? AND doc_type=?", (app_id, doc_type)
    ).fetchone()
    if existing:
        conn.close()
        return {"status": "already exists"}
    conn.execute(
        "INSERT INTO documents (app_id, doc_type, status) VALUES (?,?,?)",
        (app_id, doc_type, "missing")
    )
    conn.commit()
    conn.close()
    return {"status": "added", "doc_type": doc_type}


# ── DELETE client ─────────────────────────────────────────────────────────────
@app.delete("/admin/client/{client_id}")
def admin_delete_client(client_id: int, admin=Depends(require_admin)):
    """Remove a client and all their data."""
    conn = get_db()
    client = conn.execute("SELECT name FROM clients WHERE id=?", (client_id,)).fetchone()
    if not client:
        conn.close()
        raise HTTPException(404, "Client not found")
    # Cascade delete
    apps = conn.execute("SELECT app_id FROM applications WHERE client_id=?", (client_id,)).fetchall()
    for a in apps:
        conn.execute("DELETE FROM documents WHERE app_id=?", (a["app_id"],))
        conn.execute("DELETE FROM activity_log WHERE app_id=?", (a["app_id"],))
        conn.execute("DELETE FROM notifications WHERE app_id=?", (a["app_id"],))
    conn.execute("DELETE FROM applications WHERE client_id=?", (client_id,))
    conn.execute("DELETE FROM client_discounts WHERE client_id=?", (client_id,))
    conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "client": client["name"]}


# ══════════════════════════════════════════════════════════════════════════════
# PASSPORT OCR — Extract client details from uploaded passport image/PDF
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/admin/client/{client_id}/extract-passport")
async def extract_passport_details(client_id: int, admin=Depends(require_admin)):
    """
    Try to extract name, DOB, passport number, nationality, expiry from
    the stored passport image using pytesseract. Falls back gracefully if
    tesseract is not installed on the Render instance.
    """
    import base64, re

    conn = get_db()
    row  = conn.execute(
        "SELECT passport_b64, passport_filename FROM clients WHERE id=?", (client_id,)
    ).fetchone()
    conn.close()

    if not row or not row["passport_b64"]:
        raise HTTPException(404, "No passport on file")

    # Try OCR
    try:
        import pytesseract
        from PIL import Image
        import io

        img_bytes = base64.b64decode(row["passport_b64"])
        filename  = row["passport_filename"] or ""

        if filename.lower().endswith(".pdf"):
            # Convert first PDF page to image
            try:
                import fitz  # PyMuPDF
                doc  = fitz.open(stream=img_bytes, filetype="pdf")
                page = doc[0]
                pix  = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
            except Exception:
                return {"error": "PDF OCR requires PyMuPDF — install it or upload a JPG scan"}

        img  = Image.open(io.BytesIO(img_bytes))
        text = pytesseract.image_to_string(img, lang="eng")

        # Parse MRZ lines (last 2 lines of passport)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        mrz   = [l for l in lines if len(l) >= 30 and "<" in l]

        extracted = {}

        # Try MRZ parsing if available
        if len(mrz) >= 2:
            m1 = mrz[-2].replace(" ", "")
            m2 = mrz[-1].replace(" ", "")
            # Line 1: surname<<given names
            name_part = m1[5:44] if len(m1) > 44 else ""
            if "<<" in name_part:
                parts = name_part.split("<<")
                extracted["surname"]    = parts[0].replace("<", " ").strip()
                extracted["given_name"] = parts[1].replace("<", " ").strip() if len(parts) > 1 else ""
            # Line 2: passport number, DOB, expiry
            if len(m2) >= 28:
                extracted["passport_number"] = m2[0:9].replace("<", "")
                dob_raw = m2[13:19]
                exp_raw = m2[19:25]
                extracted["date_of_birth"] = _fmt_mrz_date(dob_raw)
                extracted["expiry_date"]   = _fmt_mrz_date(exp_raw)
                extracted["nationality"]   = m2[10:13].replace("<", "")
                extracted["sex"]           = m2[20] if len(m2) > 20 else ""
        else:
            # Fallback: regex scan for common patterns
            passport_re = re.compile(r'\b[A-Z]\d{7,8}\b')
            date_re     = re.compile(r'\b(\d{2}[\/\-\.]\d{2}[\/\-\.]\d{2,4}|\d{2}\s(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s\d{4})\b', re.I)
            pn = passport_re.findall(text)
            dt = date_re.findall(text)
            if pn: extracted["passport_number"] = pn[0]
            if dt: extracted["date_of_birth"] = dt[0]
            if len(dt) > 1: extracted["expiry_date"] = dt[-1]

        extracted["raw_text"] = text[:800]
        return {"status": "extracted", "data": extracted}

    except ImportError:
        return {
            "status":  "ocr_unavailable",
            "message": "pytesseract not installed. Add 'pytesseract' and 'Pillow' to requirements.txt and set TESSDATA_PREFIX on Render.",
            "data":    {}
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "data": {}}


def _fmt_mrz_date(s: str) -> str:
    """Convert YYMMDD to DD/MM/YYYY."""
    try:
        yy, mm, dd = s[0:2], s[2:4], s[4:6]
        year = int(yy)
        full_year = 2000 + year if year <= 30 else 1900 + year
        return f"{dd}/{mm}/{full_year}"
    except Exception:
        return s


# ══════════════════════════════════════════════════════════════════════════════
# HOTEL / ACCOMMODATION CRM
# ══════════════════════════════════════════════════════════════════════════════

class HotelRecord(BaseModel):
    client_id:      int
    app_id:         Optional[str] = None
    hotel_name:     str
    city:           str
    country:        str
    check_in:       str
    check_out:      str
    booking_ref:    Optional[str] = ""
    booking_status: str = "confirmed"      # confirmed | tentative | cancelled
    room_type:      Optional[str] = ""
    price_per_night: Optional[float] = None
    total_price:    Optional[float] = None
    currency:       str = "INR"
    notes:          Optional[str] = ""
    is_future:      int = 0                # 0=current, 1=future booking


@app.post("/admin/hotel")
def create_hotel_record(data: HotelRecord, admin=Depends(require_roles("visa_staff"))):
    """Create a hotel/accommodation record for a client."""
    conn = get_db()
    conn.execute("""
        INSERT INTO hotel_records
        (client_id, app_id, hotel_name, city, country, check_in, check_out,
         booking_ref, booking_status, room_type, price_per_night, total_price,
         currency, notes, is_future, created_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data.client_id, data.app_id, data.hotel_name, data.city, data.country,
        data.check_in, data.check_out, data.booking_ref, data.booking_status,
        data.room_type, data.price_per_night, data.total_price,
        data.currency, data.notes, data.is_future, admin["name"]
    ))
    if data.app_id:
        conn.execute(
            "INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
            (data.app_id, f"admin:{admin['name']}", "Hotel added",
             f"{data.hotel_name}, {data.city} ({data.check_in} → {data.check_out})")
        )
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status": "created", "id": new_id}


@app.get("/admin/hotels/{client_id}")
def get_client_hotels(client_id: int, admin=Depends(require_admin)):
    """Get all hotel records for a client."""
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM hotel_records
        WHERE client_id=?
        ORDER BY check_in ASC
    """, (client_id,)).fetchall()
    conn.close()
    current = [dict(r) for r in rows if not r["is_future"]]
    future  = [dict(r) for r in rows if r["is_future"]]
    return {"current": current, "future": future, "total": len(rows)}


@app.put("/admin/hotel/{hotel_id}")
def update_hotel_record(hotel_id: int, data: dict, admin=Depends(require_roles("visa_staff"))):
    """Update a hotel record."""
    conn = get_db()
    allowed = ["hotel_name","city","country","check_in","check_out","booking_ref",
               "booking_status","room_type","price_per_night","total_price","notes","is_future"]
    sets   = []
    values = []
    for k, v in data.items():
        if k in allowed:
            sets.append(f"{k}=?")
            values.append(v)
    if sets:
        values.append(hotel_id)
        conn.execute(f"UPDATE hotel_records SET {', '.join(sets)} WHERE id=?", values)
        conn.commit()
    conn.close()
    return {"status": "updated"}


@app.delete("/admin/hotel/{hotel_id}")
def delete_hotel_record(hotel_id: int, admin=Depends(require_roles("visa_staff"))):
    conn = get_db()
    conn.execute("DELETE FROM hotel_records WHERE id=?", (hotel_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@app.get("/admin/hotels/export/all")
def export_all_hotels(admin=Depends(require_admin)):
    """Export all hotel records as JSON for Excel generation."""
    conn = get_db()
    rows = conn.execute("""
        SELECT h.*, c.name as client_name, c.email as client_email, c.phone as client_phone
        FROM hotel_records h
        JOIN clients c ON c.id = h.client_id
        ORDER BY h.check_in ASC
    """).fetchall()
    conn.close()
    return {"hotels": [dict(r) for r in rows]}


# ══════════════════════════════════════════════════════════════════════════════
# STAFF MANAGEMENT — superadmin appoints staff and assigns roles
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/staff")
def list_staff(admin=Depends(require_superadmin)):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, email, role, active, created_at FROM admin_users ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return {"staff": [dict(r) for r in rows]}


@app.post("/admin/staff")
def create_staff(data: NewStaffRequest, admin=Depends(require_superadmin)):
    from auth import ALL_ROLES
    if data.role not in ALL_ROLES:
        raise HTTPException(400, f"Role must be one of: {', '.join(ALL_ROLES)}")
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO admin_users (name, email, password, role) VALUES (?,?,?,?)",
            (data.name, data.email, hash_password(data.password), data.role)
        )
        conn.commit()
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return {"status": "created", "id": new_id}
    except Exception as e:
        conn.close()
        raise HTTPException(400, f"Could not create staff (duplicate email?): {e}")


@app.put("/admin/staff/{staff_id}")
def update_staff(staff_id: int, data: UpdateStaffRequest, admin=Depends(require_superadmin)):
    conn = get_db()
    target = conn.execute("SELECT * FROM admin_users WHERE id=?", (staff_id,)).fetchone()
    if not target:
        conn.close()
        raise HTTPException(404, "Staff member not found")

    if target["role"] == "superadmin" and admin.get("id") != staff_id and data.active == 0:
        conn.close()
        raise HTTPException(400, "Cannot deactivate the superadmin account")

    sets, values = [], []
    if data.name is not None:
        sets.append("name=?"); values.append(data.name)
    if data.role is not None:
        from auth import ALL_ROLES
        if data.role not in ALL_ROLES:
            conn.close()
            raise HTTPException(400, f"Role must be one of: {', '.join(ALL_ROLES)}")
        sets.append("role=?"); values.append(data.role)
    if data.active is not None:
        sets.append("active=?"); values.append(data.active)
    if data.password:
        sets.append("password=?"); values.append(hash_password(data.password))

    if sets:
        values.append(staff_id)
        conn.execute(f"UPDATE admin_users SET {', '.join(sets)} WHERE id=?", values)
        conn.commit()
    conn.close()
    return {"status": "updated"}


@app.delete("/admin/staff/{staff_id}")
def delete_staff(staff_id: int, admin=Depends(require_superadmin)):
    conn = get_db()
    target = conn.execute("SELECT role FROM admin_users WHERE id=?", (staff_id,)).fetchone()
    if not target:
        conn.close()
        raise HTTPException(404, "Staff member not found")
    if target["role"] == "superadmin":
        conn.close()
        raise HTTPException(400, "Cannot delete the superadmin account")
    conn.execute("DELETE FROM admin_users WHERE id=?", (staff_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


# ══════════════════════════════════════════════════════════════════════════════
# LEADS & FOLLOW-UPS — track inquiries before they become paying clients
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/leads")
def list_leads(status: Optional[str] = None, admin=Depends(require_roles("sales"))):
    conn = get_db()
    if status:
        rows = conn.execute("""
            SELECT l.*, a.name as assigned_name
            FROM leads l LEFT JOIN admin_users a ON a.id = l.assigned_to
            WHERE l.status=? ORDER BY l.created_at DESC
        """, (status,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT l.*, a.name as assigned_name
            FROM leads l LEFT JOIN admin_users a ON a.id = l.assigned_to
            ORDER BY l.created_at DESC
        """).fetchall()

    lead_ids = [r["id"] for r in rows]
    next_followups = {}
    if lead_ids:
        placeholders = ",".join("?" * len(lead_ids))
        fu_rows = conn.execute(f"""
            SELECT lead_id, MIN(due_at) as next_due
            FROM lead_followups
            WHERE status='pending' AND lead_id IN ({placeholders})
            GROUP BY lead_id
        """, lead_ids).fetchall()
        next_followups = {r["lead_id"]: r["next_due"] for r in fu_rows}

    conn.close()
    leads = []
    for r in rows:
        d = dict(r)
        d["next_followup"] = next_followups.get(r["id"])
        leads.append(d)

    stats = {
        "new":       sum(1 for l in leads if l["status"] == "new"),
        "contacted": sum(1 for l in leads if l["status"] == "contacted"),
        "qualified": sum(1 for l in leads if l["status"] == "qualified"),
        "quoted":    sum(1 for l in leads if l["status"] == "quoted"),
        "won":       sum(1 for l in leads if l["status"] == "won"),
        "lost":      sum(1 for l in leads if l["status"] == "lost"),
        "total":     len(leads),
    }
    return {"leads": leads, "stats": stats}


@app.get("/admin/lead/{lead_id}")
def get_lead(lead_id: int, admin=Depends(require_roles("sales"))):
    conn = get_db()
    lead = conn.execute("""
        SELECT l.*, a.name as assigned_name
        FROM leads l LEFT JOIN admin_users a ON a.id = l.assigned_to
        WHERE l.id=?
    """, (lead_id,)).fetchone()
    if not lead:
        conn.close()
        raise HTTPException(404, "Lead not found")
    followups = conn.execute(
        "SELECT * FROM lead_followups WHERE lead_id=? ORDER BY due_at DESC", (lead_id,)
    ).fetchall()
    conn.close()
    return {"lead": dict(lead), "followups": [dict(f) for f in followups]}


@app.post("/admin/leads")
def create_lead(data: NewLeadRequest, admin=Depends(require_roles("sales"))):
    conn = get_db()
    conn.execute("""
        INSERT INTO leads (name, email, phone, destination, visa_type, source, notes, assigned_to, created_by)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (data.name, data.email, data.phone, data.destination, data.visa_type,
          data.source, data.notes, data.assigned_to, admin["name"]))
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status": "created", "id": new_id}


@app.put("/admin/lead/{lead_id}")
def update_lead(lead_id: int, data: UpdateLeadRequest, admin=Depends(require_roles("sales"))):
    conn = get_db()
    lead = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not lead:
        conn.close()
        raise HTTPException(404, "Lead not found")

    sets, values = ["updated_at=CURRENT_TIMESTAMP"], []
    fields = {
        "name": data.name, "email": data.email, "phone": data.phone,
        "destination": data.destination, "visa_type": data.visa_type,
        "status": data.status, "assigned_to": data.assigned_to, "notes": data.notes,
    }
    for col, val in fields.items():
        if val is not None:
            sets.append(f"{col}=?")
            values.append(val)
    if len(sets) > 1:
        values.append(lead_id)
        conn.execute(f"UPDATE leads SET {', '.join(sets)} WHERE id=?", values)
        conn.commit()
    conn.close()
    return {"status": "updated"}


@app.delete("/admin/lead/{lead_id}")
def delete_lead(lead_id: int, admin=Depends(require_roles("sales"))):
    conn = get_db()
    conn.execute("DELETE FROM lead_followups WHERE lead_id=?", (lead_id,))
    conn.execute("DELETE FROM leads WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@app.post("/admin/lead/{lead_id}/convert")
def convert_lead_to_client(lead_id: int, data: ConvertLeadRequest, admin=Depends(require_roles("sales"))):
    """Convert a won lead into a real client + application."""
    conn = get_db()
    lead = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not lead:
        conn.close()
        raise HTTPException(404, "Lead not found")
    if not lead["email"]:
        conn.close()
        raise HTTPException(400, "Lead needs an email address before converting")

    existing = conn.execute("SELECT id FROM clients WHERE email=?", (lead["email"],)).fetchone()
    if existing:
        client_id = existing["id"]
    else:
        conn.execute(
            "INSERT INTO clients (name, email, phone, password) VALUES (?,?,?,?)",
            (lead["name"], lead["email"], lead["phone"], hash_password(data.password))
        )
        client_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    count  = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    app_id = f"VIS-{now_ist().year}-{str(count+1).zfill(3)}"

    conn.execute("""
        INSERT INTO applications (app_id, client_id, destination, visa_type, status, progress)
        VALUES (?,?,?,?,?,?)
    """, (app_id, client_id, lead["destination"] or "TBD", lead["visa_type"] or "tourist", "pending", 10))

    conn.execute(
        "UPDATE leads SET status='won', converted_client_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (client_id, lead_id)
    )
    conn.execute(
        "INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
        (app_id, f"admin:{admin['name']}", "Lead converted", f"Converted from lead #{lead_id}")
    )
    conn.commit()
    conn.close()
    return {"status": "converted", "client_id": client_id, "app_id": app_id}


@app.post("/admin/lead/{lead_id}/followup")
def add_followup(lead_id: int, data: NewFollowupRequest, admin=Depends(require_roles("sales"))):
    conn = get_db()
    lead = conn.execute("SELECT id FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not lead:
        conn.close()
        raise HTTPException(404, "Lead not found")
    conn.execute("""
        INSERT INTO lead_followups (lead_id, due_at, note, channel, created_by)
        VALUES (?,?,?,?,?)
    """, (lead_id, data.due_at, data.note, data.channel, admin["name"]))
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status": "created", "id": new_id}


@app.post("/admin/followup/{followup_id}/complete")
def complete_followup(followup_id: int, admin=Depends(require_roles("sales"))):
    conn = get_db()
    conn.execute(
        "UPDATE lead_followups SET status='done', completed_at=CURRENT_TIMESTAMP WHERE id=?",
        (followup_id,)
    )
    conn.commit()
    conn.close()
    return {"status": "completed"}


@app.delete("/admin/followup/{followup_id}")
def delete_followup(followup_id: int, admin=Depends(require_roles("sales"))):
    conn = get_db()
    conn.execute("DELETE FROM lead_followups WHERE id=?", (followup_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@app.get("/admin/followups/due")
def get_due_followups(admin=Depends(require_roles("sales"))):
    """All pending follow-ups due today or overdue — for dashboard widget."""
    conn = get_db()
    rows = conn.execute("""
        SELECT f.*, l.name as lead_name, l.phone as lead_phone, l.destination
        FROM lead_followups f
        JOIN leads l ON l.id = f.lead_id
        WHERE f.status='pending' AND f.due_at <= datetime('now', '+1 day')
        ORDER BY f.due_at ASC
    """).fetchall()
    conn.close()
    return {"followups": [dict(r) for r in rows]}


# ══════════════════════════════════════════════════════════════════════════════
# CALENDAR — visa appointments, travel dates, deadlines
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/calendar")
def list_calendar_events(
    start: Optional[str] = None,
    end:   Optional[str] = None,
    admin=Depends(require_admin)
):
    """List calendar events, optionally filtered by date range (YYYY-MM-DD)."""
    conn = get_db()
    query  = """
        SELECT e.*, c.name as client_name, l.name as lead_name
        FROM calendar_events e
        LEFT JOIN clients c ON c.id = e.client_id
        LEFT JOIN leads l ON l.id = e.lead_id
    """
    params = []
    if start and end:
        query += " WHERE e.start_at >= ? AND e.start_at <= ?"
        params = [start, end]
    query += " ORDER BY e.start_at ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return {"events": [dict(r) for r in rows]}


@app.get("/admin/calendar/upcoming")
def upcoming_calendar_events(admin=Depends(require_admin)):
    """Next 14 days of events — for dashboard widget."""
    conn = get_db()
    rows = conn.execute("""
        SELECT e.*, c.name as client_name, l.name as lead_name
        FROM calendar_events e
        LEFT JOIN clients c ON c.id = e.client_id
        LEFT JOIN leads l ON l.id = e.lead_id
        WHERE e.start_at >= datetime('now') AND e.start_at <= datetime('now', '+14 day')
        ORDER BY e.start_at ASC
        LIMIT 20
    """).fetchall()
    conn.close()
    return {"events": [dict(r) for r in rows]}


@app.post("/admin/calendar")
def create_calendar_event(data: NewCalendarEventRequest, admin=Depends(require_admin)):
    conn = get_db()

    reminder_email = data.reminder_email
    if data.reminder_minutes_before is not None and not reminder_email:
        # Default to the creating staff member's own email
        row = conn.execute("SELECT email FROM admin_users WHERE name=?", (admin["name"],)).fetchone()
        reminder_email = row["email"] if row else None

    conn.execute("""
        INSERT INTO calendar_events
        (title, event_type, start_at, end_at, all_day, client_id, app_id, lead_id, location, notes, color,
         reminder_minutes_before, reminder_email, created_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data.title, data.event_type, data.start_at, data.end_at, data.all_day,
        data.client_id, data.app_id, data.lead_id, data.location, data.notes,
        data.color, data.reminder_minutes_before, reminder_email, admin["name"]
    ))
    if data.app_id:
        conn.execute(
            "INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
            (data.app_id, f"admin:{admin['name']}", "Calendar event added",
             f"{data.title} on {data.start_at}")
        )
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status": "created", "id": new_id}


@app.put("/admin/calendar/{event_id}")
def update_calendar_event(event_id: int, data: UpdateCalendarEventRequest, admin=Depends(require_admin)):
    conn = get_db()
    event = conn.execute("SELECT id FROM calendar_events WHERE id=?", (event_id,)).fetchone()
    if not event:
        conn.close()
        raise HTTPException(404, "Event not found")
    sets, values = [], []
    for col, val in data.dict(exclude_unset=True).items():
        sets.append(f"{col}=?")
        values.append(val)
    if sets:
        values.append(event_id)
        conn.execute(f"UPDATE calendar_events SET {', '.join(sets)} WHERE id=?", values)
        conn.commit()
    conn.close()
    return {"status": "updated"}


@app.delete("/admin/calendar/{event_id}")
def delete_calendar_event(event_id: int, admin=Depends(require_admin)):
    conn = get_db()
    conn.execute("DELETE FROM calendar_events WHERE id=?", (event_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@app.get("/admin/calendar/due-reminders")
def check_due_reminders(admin=Depends(require_admin)):
    """
    Called whenever staff load the app. Finds events whose reminder time
    has arrived but the email hasn't been sent yet, fires the email, marks
    it sent, and returns events that should pop up in-browser for THIS
    staff member (based on whether they've already dismissed it).
    """
    conn = get_db()

    # 1) Send any due, unsent email reminders
    due_for_email = conn.execute("""
        SELECT * FROM calendar_events
        WHERE reminder_minutes_before IS NOT NULL
          AND reminder_sent = 0
          AND reminder_email IS NOT NULL
          AND datetime(start_at, '-' || reminder_minutes_before || ' minutes') <= datetime('now')
    """).fetchall()

    for ev in due_for_email:
        send_calendar_reminder(
            ev["reminder_email"], ev["title"], ev["event_type"],
            ev["start_at"], ev["location"] or "", ev["notes"] or ""
        )
        conn.execute("UPDATE calendar_events SET reminder_sent=1 WHERE id=?", (ev["id"],))

    if due_for_email:
        conn.commit()

    # 2) Find events that should pop up for THIS staff member:
    #    reminder window has started, event hasn't happened yet, and this
    #    staff member hasn't dismissed the popup yet.
    staff_name = admin["name"]
    candidates = conn.execute("""
        SELECT * FROM calendar_events
        WHERE reminder_minutes_before IS NOT NULL
          AND start_at >= datetime('now')
          AND datetime(start_at, '-' || reminder_minutes_before || ' minutes') <= datetime('now')
    """).fetchall()

    popups = []
    for ev in candidates:
        seen = json.loads(ev["popup_seen_by"] or "[]")
        if staff_name not in seen:
            popups.append(dict(ev))

    conn.close()
    return {"popups": popups, "emails_sent": len(due_for_email)}


@app.post("/admin/calendar/{event_id}/dismiss-popup")
def dismiss_calendar_popup(event_id: int, data: DismissPopupRequest, admin=Depends(require_admin)):
    """Mark this popup as seen by this specific staff member (not globally)."""
    conn = get_db()
    ev = conn.execute("SELECT popup_seen_by FROM calendar_events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        conn.close()
        raise HTTPException(404, "Event not found")
    seen = json.loads(ev["popup_seen_by"] or "[]")
    if data.staff_name not in seen:
        seen.append(data.staff_name)
    conn.execute("UPDATE calendar_events SET popup_seen_by=? WHERE id=?", (json.dumps(seen), event_id))
    conn.commit()
    conn.close()
    return {"status": "dismissed"}


# ══════════════════════════════════════════════════════════════════════════════
# TEAM CHAT — global channel, all staff see the same messages
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/team-chat")
def get_team_chat(since_id: int = 0, admin=Depends(require_admin)):
    """
    Returns messages newer than since_id. Pass since_id=0 for full history
    (capped at the most recent 200), or pass the last message id you have
    to poll for new messages only.
    """
    conn = get_db()
    if since_id:
        rows = conn.execute(
            "SELECT * FROM team_chat_messages WHERE id > ? ORDER BY id ASC", (since_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM team_chat_messages ORDER BY id DESC LIMIT 200"
        ).fetchall()
        rows = list(reversed(rows))
    conn.close()
    return {"messages": [dict(r) for r in rows]}


@app.post("/admin/team-chat")
def post_team_chat(data: TeamChatMessageRequest, admin=Depends(require_admin)):
    message = data.message.strip()
    if not message:
        raise HTTPException(400, "Message cannot be empty")
    conn = get_db()
    row = conn.execute("SELECT id, role FROM admin_users WHERE name=?", (admin["name"],)).fetchone()
    conn.execute(
        "INSERT INTO team_chat_messages (sender_id, sender_name, sender_role, message) VALUES (?,?,?,?)",
        (row["id"] if row else None, admin["name"], row["role"] if row else admin.get("role"), message)
    )
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status": "sent", "id": new_id}


# ══════════════════════════════════════════════════════════════════════════════
# INVOICES & PAYMENTS
# ══════════════════════════════════════════════════════════════════════════════

def _calc_invoice_totals(line_items: list, service_charge: float, tax_percent: float):
    """
    service_charge is ADDED to the subtotal (not subtracted) per business rule:
    base price + service charge, then tax is applied on top of that.
    The parameter/column name 'discount' is kept internally for DB compatibility,
    but it now represents an additive service charge, not a price reduction.
    """
    subtotal     = sum(li.qty * li.unit_price for li in line_items)
    after_charge = subtotal + service_charge
    tax_amount   = after_charge * (tax_percent / 100)
    total        = after_charge + tax_amount
    return subtotal, tax_amount, total


@app.get("/admin/invoices")
def list_invoices(status: Optional[str] = None, admin=Depends(require_roles("visa_staff"))):
    conn = get_db()
    query  = """
        SELECT i.*, c.name as client_name, c.email as client_email, c.phone as client_phone
        FROM invoices i JOIN clients c ON c.id = i.client_id
    """
    params = []
    if status:
        query += " WHERE i.status=?"
        params = [status]
    query += " ORDER BY i.created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    invoices = []
    for r in rows:
        d = dict(r)
        d["line_items"] = json.loads(d["line_items_json"])
        d["balance_due"] = round((d["total"] or 0) - (d["amount_paid"] or 0), 2)
        invoices.append(d)

    stats = {
        "total_invoiced":  round(sum(i["total"] for i in invoices), 2),
        "total_collected": round(sum(i["amount_paid"] for i in invoices), 2),
        "total_due":       round(sum(i["balance_due"] for i in invoices), 2),
        "total_count":     len(invoices),
        "unpaid_count":    sum(1 for i in invoices if i["status"] == "unpaid"),
        "overdue_count":   sum(1 for i in invoices if i["status"] == "overdue"),
    }
    return {"invoices": invoices, "stats": stats}


@app.get("/admin/invoice/{invoice_id}")
def get_invoice(invoice_id: int, admin=Depends(require_roles("visa_staff"))):
    conn = get_db()
    inv = conn.execute("""
        SELECT i.*, c.name as client_name, c.email as client_email, c.phone as client_phone
        FROM invoices i JOIN clients c ON c.id = i.client_id
        WHERE i.id=?
    """, (invoice_id,)).fetchone()
    if not inv:
        conn.close()
        raise HTTPException(404, "Invoice not found")
    payments = conn.execute(
        "SELECT * FROM invoice_payments WHERE invoice_id=? ORDER BY paid_at DESC", (invoice_id,)
    ).fetchall()
    conn.close()
    d = dict(inv)
    d["line_items"] = json.loads(d["line_items_json"])
    d["balance_due"] = round((d["total"] or 0) - (d["amount_paid"] or 0), 2)
    return {"invoice": d, "payments": [dict(p) for p in payments]}


@app.post("/admin/invoice")
def create_invoice(data: NewInvoiceRequest, admin=Depends(require_roles("visa_staff"))):
    conn = get_db()
    client = conn.execute("SELECT id FROM clients WHERE id=?", (data.client_id,)).fetchone()
    if not client:
        conn.close()
        raise HTTPException(404, "Client not found")

    subtotal, tax_amount, total = _calc_invoice_totals(data.line_items, data.discount, data.tax_percent)
    count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    invoice_no = f"INV-{now_ist().year}-{str(count+1).zfill(3)}"

    line_items_json = json.dumps([
        {"label": li.label, "qty": li.qty, "unit_price": li.unit_price, "amount": round(li.qty * li.unit_price, 2)}
        for li in data.line_items
    ])

    conn.execute("""
        INSERT INTO invoices
        (invoice_no, client_id, app_id, line_items_json, subtotal, discount, tax_percent, tax_amount, total, due_date, notes, created_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        invoice_no, data.client_id, data.app_id, line_items_json,
        round(subtotal, 2), data.discount, data.tax_percent, round(tax_amount, 2),
        round(total, 2), data.due_date, data.notes, admin["name"]
    ))

    if data.app_id:
        conn.execute(
            "INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
            (data.app_id, f"admin:{admin['name']}", "Invoice created",
             f"{invoice_no} — total ₹{total:.2f}")
        )

    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status": "created", "id": new_id, "invoice_no": invoice_no, "total": round(total, 2)}


@app.put("/admin/invoice/{invoice_id}")
def update_invoice(invoice_id: int, data: UpdateInvoiceRequest, admin=Depends(require_roles("visa_staff"))):
    conn = get_db()
    inv = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    if not inv:
        conn.close()
        raise HTTPException(404, "Invoice not found")

    sets, values = ["updated_at=CURRENT_TIMESTAMP"], []

    if data.line_items is not None:
        discount    = data.discount if data.discount is not None else inv["discount"]
        tax_percent = data.tax_percent if data.tax_percent is not None else inv["tax_percent"]
        subtotal, tax_amount, total = _calc_invoice_totals(data.line_items, discount, tax_percent)
        line_items_json = json.dumps([
            {"label": li.label, "qty": li.qty, "unit_price": li.unit_price, "amount": round(li.qty * li.unit_price, 2)}
            for li in data.line_items
        ])
        sets += ["line_items_json=?", "subtotal=?", "discount=?", "tax_percent=?", "tax_amount=?", "total=?"]
        values += [line_items_json, round(subtotal, 2), discount, tax_percent, round(tax_amount, 2), round(total, 2)]
    elif data.discount is not None or data.tax_percent is not None:
        existing_items = json.loads(inv["line_items_json"])
        items = [InvoiceLineItem(label=i["label"], qty=i["qty"], unit_price=i["unit_price"]) for i in existing_items]
        discount    = data.discount if data.discount is not None else inv["discount"]
        tax_percent = data.tax_percent if data.tax_percent is not None else inv["tax_percent"]
        subtotal, tax_amount, total = _calc_invoice_totals(items, discount, tax_percent)
        sets += ["discount=?", "tax_percent=?", "tax_amount=?", "total=?"]
        values += [discount, tax_percent, round(tax_amount, 2), round(total, 2)]

    if data.due_date is not None:
        sets.append("due_date=?"); values.append(data.due_date)
    if data.notes is not None:
        sets.append("notes=?"); values.append(data.notes)
    if data.status is not None:
        sets.append("status=?"); values.append(data.status)

    values.append(invoice_id)
    conn.execute(f"UPDATE invoices SET {', '.join(sets)} WHERE id=?", values)
    conn.commit()
    conn.close()
    return {"status": "updated"}


@app.delete("/admin/invoice/{invoice_id}")
def delete_invoice(invoice_id: int, admin=Depends(require_roles("visa_staff"))):
    conn = get_db()
    conn.execute("DELETE FROM invoice_payments WHERE invoice_id=?", (invoice_id,))
    conn.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@app.post("/admin/invoice/{invoice_id}/payment")
def record_payment(invoice_id: int, data: RecordPaymentRequest, admin=Depends(require_roles("visa_staff"))):
    conn = get_db()
    inv = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    if not inv:
        conn.close()
        raise HTTPException(404, "Invoice not found")

    paid_at = data.paid_at or now_ist().strftime("%Y-%m-%d")
    conn.execute("""
        INSERT INTO invoice_payments (invoice_id, amount, method, reference, paid_at, notes, recorded_by)
        VALUES (?,?,?,?,?,?,?)
    """, (invoice_id, data.amount, data.method, data.reference, paid_at, data.notes, admin["name"]))

    new_paid  = (inv["amount_paid"] or 0) + data.amount
    new_status = "paid" if new_paid >= inv["total"] else ("partial" if new_paid > 0 else "unpaid")

    conn.execute(
        "UPDATE invoices SET amount_paid=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (round(new_paid, 2), new_status, invoice_id)
    )

    if inv["app_id"]:
        conn.execute(
            "INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
            (inv["app_id"], f"admin:{admin['name']}", "Payment recorded",
             f"₹{data.amount:.2f} via {data.method} for {inv['invoice_no']}")
        )

    conn.commit()
    conn.close()
    return {"status": "recorded", "new_status": new_status, "amount_paid": round(new_paid, 2)}


@app.get("/admin/invoices/export")
def export_invoices(admin=Depends(require_roles("visa_staff"))):
    """Flat export of all invoices for Excel/CSV download."""
    conn = get_db()
    rows = conn.execute("""
        SELECT i.*, c.name as client_name, c.email as client_email, c.phone as client_phone
        FROM invoices i JOIN clients c ON c.id = i.client_id
        ORDER BY i.created_at DESC
    """).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["balance_due"] = round((d["total"] or 0) - (d["amount_paid"] or 0), 2)
        out.append(d)
    return {"invoices": out}


# ══════════════════════════════════════════════════════════════════════════════
# IST HELPER — used by all endpoints when inserting manual timestamps
# ══════════════════════════════════════════════════════════════════════════════

def _log_staff_activity(conn, staff_name: str, staff_role: str, action: str,
                         detail: str = "", session_id: str = ""):
    """Insert a staff activity record with IST timestamp."""
    staff_row = conn.execute(
        "SELECT id FROM admin_users WHERE name=?", (staff_name,)
    ).fetchone()
    staff_id = staff_row["id"] if staff_row else None
    conn.execute("""
        INSERT INTO staff_activity_log (staff_id, staff_name, staff_role, action, detail, session_id)
        VALUES (?,?,?,?,?,?)
    """, (staff_id, staff_name, staff_role, action, detail, session_id))


# ══════════════════════════════════════════════════════════════════════════════
# STAFF ACTIVITY MONITORING — superadmin only
# ══════════════════════════════════════════════════════════════════════════════

class StaffActivityRequest(BaseModel):
    action:     str
    detail:     Optional[str] = ""
    session_id: Optional[str] = ""


@app.post("/admin/log-activity")
def log_my_activity(data: StaffActivityRequest, admin=Depends(require_admin)):
    """Called by the frontend to log actions (page visits, saves, logouts)."""
    conn = get_db()
    _log_staff_activity(conn, admin["name"], admin.get("role", ""), data.action, data.detail, data.session_id)
    conn.commit()
    conn.close()
    return {"status": "logged"}


@app.get("/admin/staff-activity")
def get_all_staff_activity(admin=Depends(require_superadmin)):
    """Superadmin: see recent activity for all staff members."""
    conn = get_db()
    rows = conn.execute("""
        SELECT sal.*, au.email
        FROM staff_activity_log sal
        LEFT JOIN admin_users au ON au.id = sal.staff_id
        ORDER BY sal.created_at DESC
        LIMIT 500
    """).fetchall()
    conn.close()
    return {"activity": [dict(r) for r in rows]}


@app.get("/admin/staff-activity/{staff_id}")
def get_staff_member_activity(staff_id: int, admin=Depends(require_superadmin)):
    """Superadmin: full activity log for one specific staff member."""
    conn = get_db()
    staff = conn.execute(
        "SELECT id, name, email, role, active, created_at FROM admin_users WHERE id=?", (staff_id,)
    ).fetchone()
    if not staff:
        conn.close()
        raise HTTPException(404, "Staff member not found")

    activity = conn.execute("""
        SELECT * FROM staff_activity_log WHERE staff_id=?
        ORDER BY created_at DESC LIMIT 200
    """, (staff_id,)).fetchall()

    # Calculate session durations from login/logout pairs
    sessions = []
    login_time = None
    for row in reversed(activity):
        if row["action"] == "login":
            login_time = row["created_at"]
        elif row["action"] == "logout" and login_time:
            sessions.append({"login": login_time, "logout": row["created_at"]})
            login_time = None

    conn.close()
    return {
        "staff":    dict(staff),
        "activity": [dict(r) for r in activity],
        "sessions": sessions
    }


@app.get("/admin/staff-online")
def get_staff_online_status(admin=Depends(require_superadmin)):
    """Return all staff with their last-seen timestamp."""
    conn = get_db()
    rows = conn.execute("""
        SELECT au.id, au.name, au.email, au.role, au.active,
               MAX(sal.created_at) as last_seen,
               MAX(CASE WHEN sal.action='login' THEN sal.created_at END) as last_login
        FROM admin_users au
        LEFT JOIN staff_activity_log sal ON sal.staff_id = au.id
        WHERE au.role != 'client'
        GROUP BY au.id
        ORDER BY last_seen DESC NULLS LAST
    """).fetchall()
    conn.close()
    return {"staff": [dict(r) for r in rows]}


# ══════════════════════════════════════════════════════════════════════════════
# DIRECT MESSAGES & PINGS — superadmin can message any staff member
# ══════════════════════════════════════════════════════════════════════════════

class DirectMessageRequest(BaseModel):
    to_id:   int
    message: str
    is_ping: int = 0   # 1 = urgent ping


@app.post("/admin/direct-message")
def send_direct_message(data: DirectMessageRequest, admin=Depends(require_superadmin)):
    conn = get_db()
    to_staff = conn.execute("SELECT id, name FROM admin_users WHERE id=?", (data.to_id,)).fetchone()
    if not to_staff:
        conn.close()
        raise HTTPException(404, "Staff member not found")
    sender = conn.execute(
        "SELECT id FROM admin_users WHERE name=?", (admin["name"],)
    ).fetchone()
    conn.execute("""
        INSERT INTO staff_direct_messages (from_id, from_name, to_id, to_name, message, is_ping)
        VALUES (?,?,?,?,?,?)
    """, (sender["id"] if sender else 0, admin["name"],
          data.to_id, to_staff["name"], data.message, data.is_ping))
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status": "sent", "id": new_id}


@app.get("/admin/direct-messages/{staff_id}")
def get_direct_messages(staff_id: int, admin=Depends(require_admin)):
    """Get conversation between superadmin and this staff member."""
    conn = get_db()
    my_id_row = conn.execute(
        "SELECT id FROM admin_users WHERE name=?", (admin["name"],)
    ).fetchone()
    my_id = my_id_row["id"] if my_id_row else 0

    rows = conn.execute("""
        SELECT * FROM staff_direct_messages
        WHERE (from_id=? AND to_id=?) OR (from_id=? AND to_id=?)
        ORDER BY created_at ASC
    """, (my_id, staff_id, staff_id, my_id)).fetchall()

    # Mark unread messages to me as read
    conn.execute("""
        UPDATE staff_direct_messages
        SET read_at = datetime('now', '+5 hours', '+30 minutes')
        WHERE to_id=? AND from_id=? AND read_at IS NULL
    """, (my_id, staff_id))
    conn.commit()
    conn.close()
    return {"messages": [dict(r) for r in rows]}


@app.get("/admin/my-messages")
def get_my_messages(admin=Depends(require_admin)):
    """Get all messages/pings addressed to me, plus unread count."""
    conn = get_db()
    my_id_row = conn.execute(
        "SELECT id FROM admin_users WHERE name=?", (admin["name"],)
    ).fetchone()
    my_id = my_id_row["id"] if my_id_row else 0

    rows = conn.execute("""
        SELECT * FROM staff_direct_messages
        WHERE to_id=? ORDER BY created_at DESC LIMIT 50
    """, (my_id,)).fetchall()
    unread = conn.execute(
        "SELECT COUNT(*) FROM staff_direct_messages WHERE to_id=? AND read_at IS NULL", (my_id,)
    ).fetchone()[0]
    conn.close()
    return {"messages": [dict(r) for r in rows], "unread": unread}


# ══════════════════════════════════════════════════════════════════════════════
# STORAGE MONITORING — check DB size and auto-export if near capacity
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/storage-status")
def storage_status(admin=Depends(require_admin)):
    """
    With Turso, we cannot check the file size directly (DB is remote).
    Instead we count total rows across key tables as a proxy for usage,
    and alert superadmins if the total row count exceeds a configurable
    threshold (default 100,000 rows). Turso free tier allows 9 GB of data
    which is far more than a visa agency will realistically hit.
    """
    conn = get_db()
    tables = [
        "clients", "applications", "documents", "communication_log",
        "invoices", "invoice_payments", "hotel_records", "leads",
        "lead_followups", "team_chat_messages", "staff_activity_log",
        "activity_log", "team_notes", "calendar_events"
    ]
    total_rows = 0
    table_counts = {}
    for table in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            table_counts[table] = count
            total_rows += count
        except Exception:
            table_counts[table] = 0

    # Also count document file storage (base64 in DB is largest consumer)
    doc_size_est = table_counts.get("documents", 0) * 0.5  # rough 0.5 MB per doc avg
    passport_size_est = table_counts.get("clients", 0) * 1.0  # rough 1 MB per passport

    max_rows  = int(os.getenv("DB_MAX_ROWS", "100000"))
    used_pct  = round((total_rows / max_rows) * 100, 1) if max_rows else 0
    near_cap  = used_pct >= 90

    if near_cap:
        admins = conn.execute(
            "SELECT email, name FROM admin_users WHERE role IN ('superadmin','staff') AND active=1"
        ).fetchall()
        from notifier import _send_email
        for a in admins:
            _send_email(
                a["email"],
                "Warning: MKOV CRM — Database Near Capacity",
                f"Warning: The CRM database has {total_rows:,} rows ({used_pct}% of the {max_rows:,} row limit).\n\n"
                f"Please export your data and contact your system administrator.",
                f"<div style='font-family:Arial;padding:20px'>"
                f"<h2 style='color:#d6403f'>Storage Warning</h2>"
                f"<p>The MKOV Visa CRM database has <strong>{total_rows:,} rows</strong> "
                f"({used_pct}% of the {max_rows:,} row limit).</p>"
                f"<p>Key counts: {', '.join(f'{k}: {v}' for k,v in table_counts.items() if v > 0)}</p>"
                f"<p>Please export your data immediately via the Export CRM page.</p></div>",
                "storage_warning"
            )
    conn.close()
    return {
        "total_rows":    total_rows,
        "max_rows":      max_rows,
        "used_percent":  used_pct,
        "near_capacity": near_cap,
        "table_counts":  table_counts,
        "estimated_storage_mb": round(doc_size_est + passport_size_est, 1),
        "status": "warning" if near_cap else "ok"
    }


# ══════════════════════════════════════════════════════════════════════════════
# INVOICE — GOVERNMENT FEE VS SERVICE FEE SPLIT
# ══════════════════════════════════════════════════════════════════════════════

class InvoiceSplitRequest(BaseModel):
    client_id:      int
    app_id:         Optional[str] = None
    service_items:  list[InvoiceLineItem]   # agency service fee items
    govt_items:     list[InvoiceLineItem]   # government/visa fee items (non-refundable)
    tax_percent:    float = 0
    due_date:       Optional[str] = None
    notes:          Optional[str] = ""

class CancelInvoiceRequest(BaseModel):
    retain_service_fee: bool = True   # if True, only refund govt portion

@app.post("/admin/invoice/split")
def create_split_invoice(data: InvoiceSplitRequest, admin=Depends(require_roles("visa_staff"))):
    """Create invoice with separate govt fee and service fee line items."""
    conn = get_db()
    client = conn.execute("SELECT id FROM clients WHERE id=?", (data.client_id,)).fetchone()
    if not client:
        conn.close(); raise HTTPException(404, "Client not found")

    service_total = sum(i.qty * i.unit_price for i in data.service_items)
    govt_total    = sum(i.qty * i.unit_price for i in data.govt_items)
    subtotal      = service_total + govt_total
    tax_amount    = subtotal * (data.tax_percent / 100)
    total         = subtotal + tax_amount

    line_items = []
    for i in data.service_items:
        line_items.append({"label": i.label, "qty": i.qty, "unit_price": i.unit_price,
                           "amount": round(i.qty * i.unit_price, 2), "type": "service"})
    for i in data.govt_items:
        line_items.append({"label": i.label, "qty": i.qty, "unit_price": i.unit_price,
                           "amount": round(i.qty * i.unit_price, 2), "type": "govt"})

    count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    invoice_no = f"INV-{now_ist().year}-{str(count+1).zfill(3)}"

    conn.execute("""
        INSERT INTO invoices
        (invoice_no, client_id, app_id, line_items_json, subtotal, discount,
         tax_percent, tax_amount, total, due_date, notes, created_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (invoice_no, data.client_id, data.app_id, json.dumps(line_items),
          round(subtotal,2), 0, data.tax_percent, round(tax_amount,2),
          round(total,2), data.due_date, data.notes, admin["name"]))

    if data.app_id:
        conn.execute("INSERT INTO activity_log (app_id,actor,action,detail) VALUES (?,?,?,?)",
                     (data.app_id, f"admin:{admin['name']}", "Invoice created",
                      f"{invoice_no} — Service: Rs.{service_total:.0f} + Govt: Rs.{govt_total:.0f}"))
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status":"created","id":new_id,"invoice_no":invoice_no,
            "service_total":service_total,"govt_total":govt_total,"total":total}

@app.post("/admin/invoice/{invoice_id}/cancel")
def cancel_invoice(invoice_id: int, data: CancelInvoiceRequest, admin=Depends(require_roles("visa_staff"))):
    """Cancel invoice. If retain_service_fee=True, only govt portion is marked as lost."""
    conn = get_db()
    inv = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    if not inv:
        conn.close(); raise HTTPException(404, "Invoice not found")

    items = json.loads(inv["line_items_json"])
    service_total = sum(i["amount"] for i in items if i.get("type") == "service")
    govt_total    = sum(i["amount"] for i in items if i.get("type") == "govt")

    if data.retain_service_fee:
        # Only govt fee lost — service fee retained by agency
        refundable = round(govt_total, 2)
        note = f"Cancelled — govt fee Rs.{govt_total:.0f} non-refundable; service fee Rs.{service_total:.0f} retained"
    else:
        refundable = round(inv["total"], 2)
        note = "Cancelled — full refund issued"

    conn.execute("UPDATE invoices SET status='cancelled', notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                 (note, invoice_id))
    if inv["app_id"]:
        conn.execute("INSERT INTO activity_log (app_id,actor,action,detail) VALUES (?,?,?,?)",
                     (inv["app_id"], f"admin:{admin['name']}", "Invoice cancelled", note))
    conn.commit(); conn.close()
    return {"status":"cancelled","refundable_amount":refundable,"note":note}


# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENT VAULT — client-level persistent storage with OCR auto-extract
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/vault/{client_id}")
def get_vault(client_id: int, admin=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute(
        "SELECT id,doc_type,file_name,file_mime,status,extracted_data,uploaded_by,uploaded_at,verified_at,notes "
        "FROM document_vault WHERE client_id=? ORDER BY uploaded_at DESC", (client_id,)
    ).fetchall()
    conn.close()
    docs = []
    for r in rows:
        d = dict(r)
        d["extracted_data"] = json.loads(d["extracted_data"]) if d["extracted_data"] else {}
        docs.append(d)
    return {"documents": docs}

@app.post("/admin/vault/{client_id}/upload")
async def vault_upload(
    client_id: int,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    admin=Depends(require_admin)
):
    """Upload a document to the client vault and auto-run OCR if it's a passport."""
    import base64
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 10 MB)")
    b64 = base64.b64encode(content).decode()
    mime = file.content_type or "application/octet-stream"

    extracted = {}
    if doc_type == "passport":
        extracted = _run_ocr(content, file.filename or "")

    conn = get_db()
    conn.execute("""
        INSERT INTO document_vault (client_id,doc_type,file_name,file_b64,file_mime,
                                    extracted_data,uploaded_by)
        VALUES (?,?,?,?,?,?,?)
    """, (client_id, doc_type, file.filename, b64, mime,
          json.dumps(extracted), admin["name"]))

    # If passport, push extracted fields to client profile as structured data
    if doc_type == "passport" and extracted:
        conn.execute(
            "UPDATE clients SET passport_b64=?, passport_filename=? WHERE id=?",
            (b64, file.filename, client_id)
        )

    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status":"uploaded","id":new_id,"extracted":extracted}

@app.get("/admin/vault/{client_id}/document/{doc_id}")
def vault_get_file(client_id: int, doc_id: int, admin=Depends(require_admin)):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM document_vault WHERE id=? AND client_id=?", (doc_id, client_id)
    ).fetchone()
    conn.close()
    if not row: raise HTTPException(404, "Document not found")
    d = dict(row)
    d["extracted_data"] = json.loads(d["extracted_data"]) if d["extracted_data"] else {}
    return d

@app.put("/admin/vault/{client_id}/document/{doc_id}/verify")
def vault_verify(client_id: int, doc_id: int, admin=Depends(require_admin)):
    conn = get_db()
    conn.execute(
        "UPDATE document_vault SET status='verified', verified_at=CURRENT_TIMESTAMP WHERE id=? AND client_id=?",
        (doc_id, client_id)
    )
    conn.commit(); conn.close()
    return {"status":"verified"}

@app.delete("/admin/vault/{client_id}/document/{doc_id}")
def vault_delete(client_id: int, doc_id: int, admin=Depends(require_admin)):
    conn = get_db()
    conn.execute("DELETE FROM document_vault WHERE id=? AND client_id=?", (doc_id, client_id))
    conn.commit(); conn.close()
    return {"status":"deleted"}

def _run_ocr(content: bytes, filename: str) -> dict:
    """Run OCR on uploaded file, return structured passport fields."""
    try:
        import pytesseract, re
        from PIL import Image
        import io
        if filename.lower().endswith(".pdf"):
            try:
                import fitz
                doc = fitz.open(stream=content, filetype="pdf")
                pix = doc[0].get_pixmap(dpi=200)
                content = pix.tobytes("png")
            except Exception:
                return {}
        img  = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(img, lang="eng")
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        mrz   = [l for l in lines if len(l) >= 30 and "<" in l]
        result = {}
        if len(mrz) >= 2:
            m1, m2 = mrz[-2].replace(" ",""), mrz[-1].replace(" ","")
            name_part = m1[5:44] if len(m1) > 44 else ""
            if "<<" in name_part:
                parts = name_part.split("<<")
                result["surname"]    = parts[0].replace("<"," ").strip()
                result["given_name"] = parts[1].replace("<"," ").strip() if len(parts)>1 else ""
                result["full_name"]  = f"{result['given_name']} {result['surname']}".strip()
            if len(m2) >= 25:
                result["passport_no"]  = m2[0:9].replace("<","")
                result["nationality"]  = m2[10:13].replace("<","")
                result["dob"]          = _fmt_mrz_date(m2[13:19])
                result["expiry_date"]  = _fmt_mrz_date(m2[19:25])
                result["sex"]          = m2[20] if len(m2)>20 else ""
        else:
            pn = re.findall(r'\b[A-Z]\d{7,8}\b', text)
            dt = re.findall(r'\b\d{2}[\/\-]\d{2}[\/\-]\d{2,4}\b', text)
            if pn: result["passport_no"] = pn[0]
            if dt: result["dob"] = dt[0]
            if len(dt)>1: result["expiry_date"] = dt[-1]
        result["raw_text"] = text[:500]
        return result
    except ImportError:
        return {"ocr_unavailable": True}
    except Exception as e:
        return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# LETTER TEMPLATES — cover, authority, invitation, performa
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_TEMPLATES = [
    {
        "template_type": "cover",
        "country": None, "visa_type": None,
        "subject": "Cover Letter for Visa Application",
        "body_template": """To,
The Visa Officer
Consulate General of {{destination}}

Subject: Cover Letter for {{visa_type}} Visa Application

Respected Sir/Madam,

I, {{client_name}}, holder of Passport No. {{passport_no}} (valid till {{expiry_date}}), hereby submit my application for a {{visa_type}} visa to {{destination}}.

I intend to travel from {{travel_date}} and have made all necessary arrangements. All supporting documents are enclosed herewith for your kind perusal.

I assure you that I will abide by all the laws and regulations of {{destination}} during my visit and return to India before the expiry of my visa.

Thanking You,
Yours Sincerely,

{{client_name}}
Date: {{today}}
"""
    },
    {
        "template_type": "authority",
        "country": None, "visa_type": None,
        "subject": "Authority Letter",
        "body_template": """AUTHORITY LETTER

Date: {{today}}

To Whom It May Concern,

I, {{client_name}}, holder of Passport No. {{passport_no}}, hereby authorise Uniglobe MKOV Travel to act on my behalf for the processing of my visa application for {{destination}}.

They are authorised to:
1. Submit my visa application documents
2. Collect my passport/visa on my behalf
3. Communicate with the consulate/embassy on my behalf

This authority letter is valid until {{expiry_date}}.

Signature: ____________________
Name: {{client_name}}
Date: {{today}}
"""
    },
    {
        "template_type": "invitation",
        "country": None, "visa_type": None,
        "subject": "Invitation Letter",
        "body_template": """INVITATION LETTER

Date: {{today}}

To,
The Visa Officer
Consulate of {{destination}}

Dear Sir/Madam,

I am writing to invite {{client_name}}, holder of Passport No. {{passport_no}}, nationality Indian, to visit {{destination}} from {{travel_date}}.

The purpose of the visit is {{visa_type}}.

I/We shall be responsible for the applicant's accommodation and other arrangements during the visit.

Sincerely,

[Inviter's Name & Signature]
[Inviter's Address]
[Contact Number]
"""
    },
    {
        "template_type": "performa",
        "country": None, "visa_type": None,
        "subject": "Application Performa",
        "body_template": """VISA APPLICATION PERFORMA
Uniglobe MKOV Travel — Application Reference: {{app_id}}

PERSONAL DETAILS
===============================
Full Name:          {{client_name}}
Date of Birth:      {{dob}}
Nationality:        Indian
Passport No:        {{passport_no}}
Passport Expiry:    {{expiry_date}}
Phone:              {{client_phone}}
Email:              {{client_email}}

TRAVEL DETAILS
===============================
Destination:        {{destination}}
Visa Type:          {{visa_type}}
Travel Date:        {{travel_date}}

DOCUMENTS CHECKLIST
===============================
{{documents_list}}

Staff Member:       ____________________
Date:               {{today}}
Agency Stamp:       ____________________
"""
    }
]

class NewLetterTemplateRequest(BaseModel):
    template_type: str
    country:       Optional[str] = None
    visa_type:     Optional[str] = None
    subject:       str
    body_template: str

class GenerateLetterRequest(BaseModel):
    template_id: int
    client_id:   int
    app_id:      Optional[str] = None

@app.get("/admin/letter-templates")
def list_letter_templates(admin=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM letter_templates ORDER BY template_type, created_at").fetchall()
    conn.close()
    return {"templates": [dict(r) for r in rows]}

@app.post("/admin/letter-templates/seed-defaults")
def seed_default_templates(admin=Depends(require_superadmin)):
    """One-time endpoint to load the four default letter templates."""
    conn = get_db()
    for t in DEFAULT_TEMPLATES:
        conn.execute("""
            INSERT INTO letter_templates (template_type,country,visa_type,subject,body_template,created_by)
            VALUES (?,?,?,?,?,?)
        """, (t["template_type"], t["country"], t["visa_type"],
              t["subject"], t["body_template"], "system"))
    conn.commit(); conn.close()
    return {"status":"seeded","count":len(DEFAULT_TEMPLATES)}

@app.post("/admin/letter-templates")
def create_letter_template(data: NewLetterTemplateRequest, admin=Depends(require_admin)):
    conn = get_db()
    conn.execute("""
        INSERT INTO letter_templates (template_type,country,visa_type,subject,body_template,created_by)
        VALUES (?,?,?,?,?,?)
    """, (data.template_type, data.country, data.visa_type,
          data.subject, data.body_template, admin["name"]))
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status":"created","id":new_id}

@app.post("/admin/letter-templates/generate")
def generate_letter(data: GenerateLetterRequest, admin=Depends(require_admin)):
    """Fill a template with real client/application data and return the rendered text."""
    conn = get_db()
    template = conn.execute("SELECT * FROM letter_templates WHERE id=?", (data.template_id,)).fetchone()
    if not template:
        conn.close(); raise HTTPException(404, "Template not found")

    client = conn.execute("SELECT * FROM clients WHERE id=?", (data.client_id,)).fetchone()
    if not client:
        conn.close(); raise HTTPException(404, "Client not found")

    app_row, docs = None, []
    if data.app_id:
        app_row = conn.execute("SELECT * FROM applications WHERE app_id=?", (data.app_id,)).fetchone()
        docs    = conn.execute(
            "SELECT doc_type FROM documents WHERE app_id=?", (data.app_id,)
        ).fetchall()

    # Pull OCR data from vault if available
    vault_passport = conn.execute(
        "SELECT extracted_data FROM document_vault WHERE client_id=? AND doc_type='passport' ORDER BY uploaded_at DESC LIMIT 1",
        (data.client_id,)
    ).fetchone()
    ocr = json.loads(vault_passport["extracted_data"]) if vault_passport and vault_passport["extracted_data"] else {}
    conn.close()

    today = now_ist().strftime("%d %B %Y")
    docs_list = "\n".join(f"[ ] {r['doc_type'].replace('_',' ').title()}" for r in docs) if docs else "[ ] See attached checklist"

    replacements = {
        "{{client_name}}":   client["name"],
        "{{client_email}}":  client["email"],
        "{{client_phone}}":  client["phone"] or "",
        "{{passport_no}}":   ocr.get("passport_no", "[PASSPORT NO]"),
        "{{expiry_date}}":   ocr.get("expiry_date", "[EXPIRY DATE]"),
        "{{dob}}":           ocr.get("dob", "[DATE OF BIRTH]"),
        "{{destination}}":   app_row["destination"] if app_row else "[DESTINATION]",
        "{{visa_type}}":     app_row["visa_type"].title() if app_row else "[VISA TYPE]",
        "{{travel_date}}":   app_row["travel_date"] if app_row else "[TRAVEL DATE]",
        "{{app_id}}":        data.app_id or "",
        "{{documents_list}}": docs_list,
        "{{today}}":         today,
    }

    body = dict(template)["body_template"]
    for placeholder, value in replacements.items():
        body = body.replace(placeholder, str(value) if value else "")

    return {
        "subject": dict(template)["subject"],
        "body":    body,
        "template_type": dict(template)["template_type"]
    }

@app.post("/admin/letter-templates/generate-pdf")
def generate_letter_pdf(data: GenerateLetterRequest, admin=Depends(require_admin)):
    """Same as generate_letter but returns a downloadable PDF."""
    letter = generate_letter(data, admin)  # reuse the text-generation logic

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(tmp.name, pagesize=A4, topMargin=25*mm, bottomMargin=25*mm,
                            leftMargin=25*mm, rightMargin=25*mm)
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle("LetterHeader", parent=styles["Heading1"], fontSize=14,
                                  textColor=colors.HexColor("#1e3a5f"), spaceAfter=16)
    body_style = ParagraphStyle("LetterBody", parent=styles["Normal"], fontSize=11, leading=17)

    story = [Paragraph("Uniglobe MKOV Travel", header_style)]
    for para in letter["body"].split("\n\n"):
        for line in para.split("\n"):
            story.append(Paragraph(line if line.strip() else "&nbsp;", body_style))
        story.append(Spacer(1, 6))
    doc.build(story)

    filename = f"{letter['template_type']}_letter.pdf"
    return FileResponse(tmp.name, filename=filename, media_type="application/pdf")

@app.put("/admin/letter-templates/{template_id}")
def update_letter_template(template_id: int, data: NewLetterTemplateRequest, admin=Depends(require_admin)):
    conn = get_db()
    conn.execute("""
        UPDATE letter_templates SET template_type=?,country=?,visa_type=?,
        subject=?,body_template=? WHERE id=?
    """, (data.template_type, data.country, data.visa_type,
          data.subject, data.body_template, template_id))
    conn.commit(); conn.close()
    return {"status":"updated"}

@app.delete("/admin/letter-templates/{template_id}")
def delete_letter_template(template_id: int, admin=Depends(require_admin)):
    conn = get_db()
    conn.execute("DELETE FROM letter_templates WHERE id=?", (template_id,))
    conn.commit(); conn.close()
    return {"status":"deleted"}


# ══════════════════════════════════════════════════════════════════════════════
# PACKAGES ↔ HOTEL CRM BRIDGE
# ══════════════════════════════════════════════════════════════════════════════

class NewPackageRequest(BaseModel):
    name:            str
    country:         str
    visa_type:       str
    processing_time: Optional[str] = ""
    validity:        Optional[str] = ""
    base_price:      float = 0
    documents:       list = []
    notes:           Optional[str] = ""
    hotel_ids:       list[int] = []   # hotel_record IDs to link

@app.get("/admin/packages")
def list_packages(admin=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM visa_packages ORDER BY country, visa_type").fetchall()
    packages = []
    for r in rows:
        p = dict(r)
        p["documents"] = json.loads(p["documents_json"] or "[]")
        hotel_ids = json.loads(p["hotel_ids_json"] or "[]")
        # Pull linked hotel rates live
        if hotel_ids:
            placeholders = ",".join("?" * len(hotel_ids))
            hotels = conn.execute(
                f"SELECT hotel_name,city,room_type,price_per_night,total_price,currency,check_in,check_out "
                f"FROM hotel_records WHERE id IN ({placeholders})", hotel_ids
            ).fetchall()
            p["linked_hotels"] = [dict(h) for h in hotels]
            p["total_hotel_cost"] = sum(h["total_price"] or 0 for h in hotels)
        else:
            p["linked_hotels"] = []
            p["total_hotel_cost"] = 0
        p["grand_total"] = p["base_price"] + p["total_hotel_cost"]
        packages.append(p)
    conn.close()
    return {"packages": packages}

@app.post("/admin/packages")
def create_package(data: NewPackageRequest, admin=Depends(require_admin)):
    conn = get_db()
    conn.execute("""
        INSERT INTO visa_packages (name,country,visa_type,processing_time,validity,
                                   base_price,documents_json,notes,hotel_ids_json,created_by)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (data.name, data.country, data.visa_type, data.processing_time, data.validity,
          data.base_price, json.dumps(data.documents), data.notes,
          json.dumps(data.hotel_ids), admin["name"]))
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status":"created","id":new_id}

@app.delete("/admin/packages/{pkg_id}")
def delete_package(pkg_id: int, admin=Depends(require_admin)):
    conn = get_db()
    conn.execute("DELETE FROM visa_packages WHERE id=?", (pkg_id,))
    conn.commit(); conn.close()
    return {"status":"deleted"}

@app.post("/admin/packages/{pkg_id}/export-manifest")
def export_package_manifest(pkg_id: int, admin=Depends(require_admin)):
    """Return a structured room-night manifest + visa applicant sheet for a package."""
    conn = get_db()
    pkg = conn.execute("SELECT * FROM visa_packages WHERE id=?", (pkg_id,)).fetchone()
    if not pkg:
        conn.close(); raise HTTPException(404, "Package not found")
    p = dict(pkg)
    hotel_ids = json.loads(p["hotel_ids_json"] or "[]")
    hotels = []
    if hotel_ids:
        placeholders = ",".join("?" * len(hotel_ids))
        hotels = [dict(h) for h in conn.execute(
            f"SELECT h.*,c.name as client_name,c.phone as client_phone "
            f"FROM hotel_records h JOIN clients c ON c.id=h.client_id "
            f"WHERE h.id IN ({placeholders})", hotel_ids
        ).fetchall()]
    conn.close()
    return {
        "package":       p,
        "hotel_manifest": hotels,
        "total_rooms":   len(hotels),
        "total_nights":  sum(
            max(0, (datetime.fromisoformat(h["check_out"]) - datetime.fromisoformat(h["check_in"])).days)
            for h in hotels if h.get("check_in") and h.get("check_out")
        ),
        "generated_at":  now_ist_str()
    }


# ══════════════════════════════════════════════════════════════════════════════
# APPLICATION MILESTONES + STALL DETECTION → AUTO TEAM CHAT
# ══════════════════════════════════════════════════════════════════════════════

STATUS_MILESTONES = {
    "pending":       "Document Collection",
    "docs_received": "Document Review",
    "review":        "Under Review",
    "submitted":     "Embassy Submitted",
    "approved":      "Approved",
    "rejected":      "Rejected",
}

@app.post("/admin/application/{app_id}/milestone")
def record_milestone(app_id: str, admin=Depends(require_admin)):
    """Called automatically when application status changes."""
    conn = get_db()
    app_row = conn.execute("SELECT status FROM applications WHERE app_id=?", (app_id,)).fetchone()
    if not app_row:
        conn.close(); raise HTTPException(404, "Application not found")

    milestone = STATUS_MILESTONES.get(app_row["status"], app_row["status"])
    # Close any open milestone
    conn.execute("""
        UPDATE application_milestones SET exited_at=CURRENT_TIMESTAMP
        WHERE app_id=? AND exited_at IS NULL
    """, (app_id,))
    conn.execute("""
        INSERT INTO application_milestones (app_id, milestone) VALUES (?,?)
    """, (app_id, milestone))
    conn.commit(); conn.close()
    return {"status":"recorded","milestone":milestone}

@app.get("/admin/applications/stalled")
def get_stalled_applications(admin=Depends(require_admin)):
    """
    Find applications that have been in the same status for >= 4 days
    and haven't been flagged yet. Also posts an automated team chat message.
    """
    conn = get_db()
    stalled = conn.execute("""
        SELECT m.app_id, m.milestone, m.entered_at, m.id as milestone_id,
               a.destination, a.visa_type,
               c.name as client_name,
               au.name as assigned_name
        FROM application_milestones m
        JOIN applications a ON a.app_id = m.app_id
        JOIN clients c ON c.id = a.client_id
        LEFT JOIN admin_users au ON au.id = a.assigned_to
        WHERE m.exited_at IS NULL
          AND m.stall_flagged = 0
          AND CAST((julianday('now') - julianday(m.entered_at)) AS INTEGER) >= m.stall_threshold_days
          AND a.status NOT IN ('approved','rejected','cancelled')
    """).fetchall()

    flagged = []
    for s in stalled:
        days_stuck = int((datetime.now() - datetime.fromisoformat(s["entered_at"].replace(" ","T"))).total_seconds() / 86400)
        assigned = s["assigned_name"] or "Unassigned"
        msg = (
            f"⚠️ STALL ALERT — {s['app_id']} ({s['client_name']}, "
            f"{s['destination']} {s['visa_type']}) has been in "
            f"\"{s['milestone']}\" for {days_stuck} day(s). "
            f"@{assigned} — what do we need to move this forward?"
        )
        # Post to team chat
        conn.execute("""
            INSERT INTO team_chat_messages (sender_id, sender_name, sender_role, message)
            VALUES (0, 'System', 'system', ?)
        """, (msg,))
        # Mark as flagged so we don't double-post
        conn.execute(
            "UPDATE application_milestones SET stall_flagged=1 WHERE id=?",
            (s["milestone_id"],)
        )
        flagged.append({"app_id":s["app_id"],"days":days_stuck,"milestone":s["milestone"],"message":msg})

    if flagged:
        conn.commit()
    conn.close()
    return {"stalled_count": len(flagged), "flagged": flagged}


# ══════════════════════════════════════════════════════════════════════════════
# ENHANCED LEAD → APPLICATION CONVERSION (auto-attach VFS checklist by country)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/admin/lead/{lead_id}/convert-full")
def convert_lead_full(lead_id: int, data: ConvertLeadRequest, admin=Depends(require_roles("sales"))):
    """
    Full conversion pipeline:
    1. Create client if not exists
    2. Create application with correct doc slots
    3. Auto-attach best matching VFS checklist for that country+visa_type
    4. Create document upload slots from checklist
    5. Record milestone
    """
    conn = get_db()
    lead = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not lead:
        conn.close(); raise HTTPException(404, "Lead not found")
    if not lead["email"]:
        conn.close(); raise HTTPException(400, "Lead needs an email address before converting")

    # 1 — Create client
    existing = conn.execute("SELECT id FROM clients WHERE email=?", (lead["email"],)).fetchone()
    if existing:
        client_id = existing["id"]
    else:
        import secrets
        conn.execute(
            "INSERT INTO clients (name,email,phone,password) VALUES (?,?,?,?)",
            (lead["name"], lead["email"], lead["phone"], hash_password(data.password))
        )
        client_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 2 — Create application
    count  = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    app_id = f"VIS-{now_ist().year}-{str(count+1).zfill(3)}"
    destination = lead["destination"] or "TBD"
    visa_type   = lead["visa_type"] or "tourist"

    # 3 — Find best matching VFS checklist for country+visa_type
    checklist = conn.execute("""
        SELECT * FROM custom_checklists
        WHERE LOWER(country)=LOWER(?) AND LOWER(visa_type)=LOWER(?)
        ORDER BY is_default DESC, created_at DESC LIMIT 1
    """, (destination, visa_type)).fetchone()
    if not checklist:
        checklist = conn.execute("""
            SELECT * FROM custom_checklists
            WHERE LOWER(country)=LOWER(?)
            ORDER BY is_default DESC, created_at DESC LIMIT 1
        """, (destination,)).fetchone()
    checklist_id = checklist["id"] if checklist else None

    conn.execute("""
        INSERT INTO applications (app_id,client_id,destination,visa_type,status,progress,checklist_id)
        VALUES (?,?,?,?,?,?,?)
    """, (app_id, client_id, destination, visa_type, "pending", 10, checklist_id))

    # 4 — Create document upload slots from checklist or default
    if checklist:
        docs = json.loads(checklist["documents_json"])
    else:
        doc_map = {
            "tourist":  ["passport","photo","bank_statement","hotel_booking","flight_ticket","travel_insurance"],
            "business": ["passport","photo","bank_statement","invitation_letter","flight_ticket","company_letter"],
            "student":  ["passport","photo","bank_statement","admission_letter","flight_ticket"],
            "transit":  ["passport","photo","onward_ticket"],
        }
        docs = doc_map.get(visa_type, ["passport","photo","bank_statement"])

    for dt in docs:
        doc_type = dt.lower().replace(" ", "_")
        conn.execute("INSERT INTO documents (app_id,doc_type,status) VALUES (?,?,?)",
                     (app_id, doc_type, "missing"))

    # 5 — Record milestone
    conn.execute("INSERT INTO application_milestones (app_id,milestone) VALUES (?,?)",
                 (app_id, "Document Collection"))

    # 6 — Mark lead as won
    conn.execute("""
        UPDATE leads SET status='won', converted_client_id=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (client_id, lead_id))

    conn.execute("INSERT INTO activity_log (app_id,actor,action,detail) VALUES (?,?,?,?)",
                 (app_id, f"admin:{admin['name']}", "Lead converted",
                  f"From lead #{lead_id} | Checklist: {checklist['name'] if checklist else 'default'}"))
    conn.commit()
    conn.close()

    return {
        "status":        "converted",
        "client_id":     client_id,
        "app_id":        app_id,
        "checklist_id":  checklist_id,
        "checklist_name": checklist["name"] if checklist else "Default",
        "doc_slots_created": len(docs)
    }
