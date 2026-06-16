"""
MKOV Visa Automation System — main.py (COMPLETE UPDATED VERSION v2.0)
"""
import os
import uuid
import json
import shutil
import tempfile
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional

from database import init_db, get_db
from auth import require_admin, require_client, admin_login, client_login, hash_password
from notifier import send_checklist, send_status_update, send_reminder

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
def admin_update_status(app_id: str, data: UpdateStatusRequest, admin=Depends(require_admin)):
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
def admin_create_application(data: NewApplicationRequest, admin=Depends(require_admin)):
    conn = get_db()
    client = conn.execute("SELECT * FROM clients WHERE email=?", (data.client_email,)).fetchone()
    if not client: conn.close(); raise HTTPException(404, "Client not found")
    count  = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    app_id = f"VIS-{datetime.now().year}-{str(count+1).zfill(3)}"
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
    return {"status": "created", "app_id": app_id}

@app.post("/admin/application/{app_id}/verify-doc")
def admin_verify_doc(app_id: str, data: UpdateDocStatusRequest, admin=Depends(require_admin)):
    conn = get_db()
    conn.execute("UPDATE documents SET status=?, notes=?, verified_at=CURRENT_TIMESTAMP WHERE id=?",
                 (data.status, data.notes, data.doc_id))
    conn.execute("INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
                 (app_id, f"admin:{admin['name']}", "Document verified", f"Doc {data.doc_id} → {data.status}"))
    conn.commit(); conn.close()
    return {"status": "updated"}

# --- Checklists & Pricing ──────────────────────────────────────────────────────
@app.post("/admin/checklist/create")
def create_checklist(data: CustomChecklistData, admin=Depends(require_admin)):
    final_price = data.base_price * (1 - data.discount_percentage / 100)
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
def update_checklist(checklist_id: int, data: UpdateChecklistData, admin=Depends(require_admin)):
    conn = get_db()
    if data.base_price is not None:
        conn.execute("UPDATE custom_checklists SET base_price=? WHERE id=?", (data.base_price, checklist_id))
    if data.discount_percentage is not None:
        row = conn.execute("SELECT base_price FROM custom_checklists WHERE id=?", (checklist_id,)).fetchone()
        fp = (row["base_price"] if row else 0) * (1 - data.discount_percentage/100)
        conn.execute("UPDATE custom_checklists SET discount_percentage=?, final_price=? WHERE id=?", (data.discount_percentage, fp, checklist_id))
    if data.documents is not None:
        conn.execute("UPDATE custom_checklists SET documents_json=? WHERE id=?", (json.dumps(data.documents), checklist_id))
    conn.execute("UPDATE custom_checklists SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (checklist_id,))
    conn.commit(); conn.close()
    return {"status": "updated"}

@app.post("/admin/client-discount")
def add_client_discount(data: ClientDiscountData, admin=Depends(require_admin)):
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
    now = datetime.now().isoformat()
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
    now     = datetime.now().isoformat()

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
def admin_update_application(app_id: str, data: UpdateApplicationRequest, admin=Depends(require_admin)):
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
def admin_set_client_fee(data: FeeStructureRequest, admin=Depends(require_admin)):
    """
    Set custom fee/discount for a specific client.
    discount_type: 'percentage' = e.g. 10% off
                   'fixed'      = e.g. INR 500 off
                   'none'       = full price
    """
    conn = get_db()
    client = conn.execute("SELECT id, name FROM clients WHERE id=?", (data.client_id,)).fetchone()
    if not client:
        conn.close()
        raise HTTPException(404, "Client not found")

    # Calculate final price
    if data.discount_type == "percentage":
        final = data.base_price * (1 - data.discount_value / 100)
    elif data.discount_type == "fixed":
        final = max(0, data.base_price - data.discount_value)
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
            (data.app_id, f"admin:{admin['name']}", "Fee updated",
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
def admin_delete_client_fee(fee_id: int, admin=Depends(require_admin)):
    conn = get_db()
    conn.execute("UPDATE client_discounts SET active=0 WHERE id=?", (fee_id,))
    conn.commit()
    conn.close()
    return {"status": "removed"}


# ── Add document type to an application checklist ────────────────────────────
@app.post("/admin/application/{app_id}/add-doc-type")
def admin_add_doc_type(app_id: str, data: dict, admin=Depends(require_admin)):
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
def create_hotel_record(data: HotelRecord, admin=Depends(require_admin)):
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
def update_hotel_record(hotel_id: int, data: dict, admin=Depends(require_admin)):
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
def delete_hotel_record(hotel_id: int, admin=Depends(require_admin)):
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
