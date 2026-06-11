"""
Uniglobe MKOV — Visa Automation System
FastAPI Backend v1.0.0
"""
import os
import uuid
import json
import shutil
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional

from database import init_db, get_db
from auth import (
    require_admin, require_client,
    admin_login, client_login,
    hash_password
)
from n8n_hooks import on_new_application, on_status_change, on_docs_reminder

# ── Init ──────────────────────────────────────────────────────────────────────
init_db()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(
    title="MKOV Visa System",
    description="Visa automation backend — admin + client portals",
    version="1.0.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=os.path.join(STATIC_DIR, "static")), name="static")

# ── Status config ─────────────────────────────────────────────────────────────
STATUS_PROGRESS = {
    "pending":       10,
    "docs_received": 35,
    "review":        55,
    "submitted":     75,
    "approved":      100,
    "rejected":      0,
}

# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:    str
    password: str

class NewApplicationRequest(BaseModel):
    destination:   str
    visa_type:     str
    travel_date:   Optional[str] = None
    duration_days: Optional[int] = None
    group_size:    int = 1

class UpdateStatusRequest(BaseModel):
    status: str
    note:   Optional[str] = ""

class NewClientRequest(BaseModel):
    name:     str
    email:    str
    phone:    Optional[str] = ""
    password: str

class UpdateDocStatusRequest(BaseModel):
    doc_id: int
    status: str
    notes:  Optional[str] = ""

# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "online", "service": "MKOV Visa System v1.0.0"}

@app.get("/health")
def health():
    return {"status": "ok"}

# ── Frontend serving ──────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
def serve_admin():
    path = os.path.join(STATIC_DIR, "admin.html")
    if os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse("<h2>admin.html not found in frontend/</h2>")

@app.get("/client", response_class=HTMLResponse)
def serve_client():
    path = os.path.join(STATIC_DIR, "client.html")
    if os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse("<h2>client.html not found in frontend/</h2>")

# ══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/auth/admin/login")
def admin_login_route(req: LoginRequest):
    return admin_login(req.email, req.password)

@app.post("/auth/client/login")
def client_login_route(req: LoginRequest):
    return client_login(req.email, req.password)

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/dashboard")
def admin_dashboard(admin=Depends(require_admin)):
    conn = get_db()

    total       = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    pending     = conn.execute("SELECT COUNT(*) FROM applications WHERE status='pending'").fetchone()[0]
    approved    = conn.execute("SELECT COUNT(*) FROM applications WHERE status='approved'").fetchone()[0]
    submitted   = conn.execute("SELECT COUNT(*) FROM applications WHERE status='submitted'").fetchone()[0]
    missing_docs= conn.execute("""
        SELECT COUNT(DISTINCT app_id) FROM documents WHERE status='missing'
    """).fetchone()[0]

    apps = conn.execute("""
        SELECT a.*, c.name as client_name, c.email as client_email, c.phone as client_phone
        FROM applications a
        JOIN clients c ON a.client_id = c.id
        ORDER BY a.updated_at DESC
    """).fetchall()

    conn.close()
    return {
        "stats": {
            "total": total, "pending": pending,
            "approved": approved, "submitted": submitted,
            "missing_docs": missing_docs
        },
        "applications": [dict(a) for a in apps]
    }


@app.get("/admin/application/{app_id}")
def admin_get_application(app_id: str, admin=Depends(require_admin)):
    conn = get_db()

    app = conn.execute("""
        SELECT a.*, c.name as client_name, c.email as client_email, c.phone as client_phone
        FROM applications a JOIN clients c ON a.client_id = c.id
        WHERE a.app_id = ?
    """, (app_id,)).fetchone()

    if not app:
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")

    docs = conn.execute(
        "SELECT * FROM documents WHERE app_id=?", (app_id,)
    ).fetchall()

    logs = conn.execute(
        "SELECT * FROM activity_log WHERE app_id=? ORDER BY created_at DESC", (app_id,)
    ).fetchall()

    conn.close()
    return {
        "application": dict(app),
        "documents":   [dict(d) for d in docs],
        "activity":    [dict(l) for l in logs],
    }


@app.post("/admin/application/{app_id}/status")
def admin_update_status(app_id: str, req: UpdateStatusRequest, admin=Depends(require_admin)):
    conn = get_db()

    app = conn.execute(
        "SELECT a.*, c.name, c.email, c.phone FROM applications a JOIN clients c ON a.client_id=c.id WHERE a.app_id=?",
        (app_id,)
    ).fetchone()
    if not app:
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")

    old_status = app["status"]
    progress   = STATUS_PROGRESS.get(req.status, 10)
    now        = datetime.now().isoformat()

    conn.execute(
        "UPDATE applications SET status=?, progress=?, notes=?, updated_at=? WHERE app_id=?",
        (req.status, progress, req.note, now, app_id)
    )
    conn.execute(
        "INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
        (app_id, f"admin:{admin['name']}", "Status updated",
         f"Status changed from {old_status} → {req.status}. {req.note or ''}")
    )
    # Add portal notification for client
    conn.execute(
        "INSERT INTO notifications (client_id, app_id, message) VALUES (?,?,?)",
        (app["client_id"], app_id,
         f"Your application status has been updated to: {req.status.replace('_',' ').title()}. {req.note or ''}")
    )
    conn.commit()
    conn.close()

    # Fire n8n webhook
    on_status_change(
        app_id=app_id,
        client_name=app["name"],
        client_phone=app["phone"] or "",
        client_email=app["email"],
        old_status=old_status,
        new_status=req.status,
        note=req.note or "",
    )

    return {"status": "updated", "app_id": app_id, "new_status": req.status}


@app.post("/admin/application/{app_id}/document/{doc_id}")
def admin_update_doc_status(
    app_id: str, doc_id: int,
    req: UpdateDocStatusRequest,
    admin=Depends(require_admin)
):
    conn = get_db()
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE documents SET status=?, notes=?, verified_at=? WHERE id=? AND app_id=?",
        (req.status, req.notes, now if req.status == "verified" else None, doc_id, app_id)
    )
    conn.execute(
        "INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
        (app_id, f"admin:{admin['name']}", "Document updated",
         f"Document #{doc_id} status set to {req.status}")
    )
    conn.commit()
    conn.close()
    return {"status": "updated"}


@app.post("/admin/clients")
def admin_create_client(req: NewClientRequest, admin=Depends(require_admin)):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO clients (name, email, phone, password) VALUES (?,?,?,?)",
            (req.name, req.email, req.phone, hash_password(req.password))
        )
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Could not create client: {str(e)}")
    conn.close()
    return {"status": "created", "email": req.email}


@app.post("/admin/application")
def admin_create_application(
    client_email: str = Form(...),
    destination:  str = Form(...),
    visa_type:    str = Form(...),
    travel_date:  str = Form(""),
    admin=Depends(require_admin)
):
    conn = get_db()
    client = conn.execute("SELECT * FROM clients WHERE email=?", (client_email,)).fetchone()
    if not client:
        conn.close()
        raise HTTPException(status_code=404, detail="Client not found")

    # Generate app ID
    count  = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    app_id = f"VIS-{datetime.now().year}-{str(count+1).zfill(3)}"

    conn.execute("""
        INSERT INTO applications (app_id, client_id, destination, visa_type, travel_date)
        VALUES (?,?,?,?,?)
    """, (app_id, client["id"], destination, visa_type, travel_date))

    # Create default doc requirements per visa type
    doc_map = {
        "tourist":  ["passport","photo","bank_statement","hotel_booking","flight_ticket","travel_insurance"],
        "business": ["passport","photo","bank_statement","invitation_letter","flight_ticket","company_letter"],
        "student":  ["passport","photo","bank_statement","admission_letter","flight_ticket","accommodation_proof"],
        "transit":  ["passport","photo","onward_ticket"],
    }
    for dt in doc_map.get(visa_type, ["passport","photo","bank_statement"]):
        conn.execute(
            "INSERT INTO documents (app_id, doc_type, status) VALUES (?,?,?)",
            (app_id, dt, "missing")
        )

    conn.execute(
        "INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
        (app_id, f"admin:{admin['name']}", "Application created",
         f"New {visa_type} visa application for {destination}")
    )
    conn.commit()
    conn.close()

    on_new_application(
        app_id=app_id,
        client_name=client["name"],
        client_phone=client["phone"] or "",
        destination=destination,
        visa_type=visa_type,
    )

    return {"status": "created", "app_id": app_id}


@app.get("/admin/webhook-log")
def admin_webhook_log(admin=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM webhook_log ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# CLIENT ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/client/dashboard")
def client_dashboard(client=Depends(require_client)):
    conn = get_db()
    client_row = conn.execute(
        "SELECT * FROM clients WHERE email=?", (client["sub"],)
    ).fetchone()
    if not client_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Client not found")

    apps = conn.execute(
        "SELECT * FROM applications WHERE client_id=? ORDER BY created_at DESC",
        (client_row["id"],)
    ).fetchall()

    notifications = conn.execute(
        "SELECT * FROM notifications WHERE client_id=? ORDER BY created_at DESC LIMIT 10",
        (client_row["id"],)
    ).fetchall()

    conn.close()
    return {
        "client":        dict(client_row),
        "applications":  [dict(a) for a in apps],
        "notifications": [dict(n) for n in notifications],
        "unread_count":  sum(1 for n in notifications if not n["read"]),
    }


@app.get("/client/application/{app_id}")
def client_get_application(app_id: str, client=Depends(require_client)):
    conn = get_db()
    client_row = conn.execute(
        "SELECT * FROM clients WHERE email=?", (client["sub"],)
    ).fetchone()

    app = conn.execute(
        "SELECT * FROM applications WHERE app_id=? AND client_id=?",
        (app_id, client_row["id"])
    ).fetchone()
    if not app:
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")

    docs = conn.execute(
        "SELECT * FROM documents WHERE app_id=?", (app_id,)
    ).fetchall()
    logs = conn.execute(
        "SELECT * FROM activity_log WHERE app_id=? ORDER BY created_at DESC", (app_id,)
    ).fetchall()

    conn.close()
    return {
        "application": dict(app),
        "documents":   [dict(d) for d in docs],
        "activity":    [dict(l) for l in logs],
    }


@app.post("/client/application/{app_id}/upload")
async def client_upload_doc(
    app_id:   str,
    doc_type: str = Form(...),
    file:     UploadFile = File(...),
    client=Depends(require_client)
):
    conn = get_db()
    client_row = conn.execute(
        "SELECT * FROM clients WHERE email=?", (client["sub"],)
    ).fetchone()

    app = conn.execute(
        "SELECT * FROM applications WHERE app_id=? AND client_id=?",
        (app_id, client_row["id"])
    ).fetchone()
    if not app:
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")

    # Save file
    ext       = os.path.splitext(file.filename)[1]
    file_name = f"{app_id}_{doc_type}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    now = datetime.now().isoformat()
    conn.execute("""
        UPDATE documents SET status='uploaded', file_name=?, file_path=?, uploaded_at=?
        WHERE app_id=? AND doc_type=?
    """, (file_name, file_path, now, app_id, doc_type))

    conn.execute(
        "INSERT INTO activity_log (app_id, actor, action, detail) VALUES (?,?,?,?)",
        (app_id, f"client:{client_row['name']}", "Document uploaded",
         f"Uploaded {doc_type}: {file_name}")
    )
    conn.commit()
    conn.close()

    return {"status": "uploaded", "file_name": file_name, "doc_type": doc_type}


@app.get("/client/document/{app_id}/{doc_type}")
def client_get_document(app_id: str, doc_type: str, client=Depends(require_client)):
    conn = get_db()
    client_row = conn.execute(
        "SELECT * FROM clients WHERE email=?", (client["sub"],)
    ).fetchone()
    app = conn.execute(
        "SELECT * FROM applications WHERE app_id=? AND client_id=?",
        (app_id, client_row["id"])
    ).fetchone()
    if not app:
        conn.close()
        raise HTTPException(status_code=403, detail="Not authorised")

    doc = conn.execute(
        "SELECT * FROM documents WHERE app_id=? AND doc_type=?", (app_id, doc_type)
    ).fetchone()
    conn.close()

    if not doc or not doc["file_path"]:
        raise HTTPException(status_code=404, detail="Document not uploaded yet")
    if not os.path.exists(doc["file_path"]):
        raise HTTPException(status_code=404, detail="File not found on server")

    return FileResponse(doc["file_path"], filename=doc["file_name"])


@app.post("/client/notifications/read-all")
def client_mark_read(client=Depends(require_client)):
    conn = get_db()
    client_row = conn.execute(
        "SELECT id FROM clients WHERE email=?", (client["sub"],)
    ).fetchone()
    conn.execute(
        "UPDATE notifications SET read=1 WHERE client_id=?", (client_row["id"],)
    )
    conn.commit()
    conn.close()
    return {"status": "all marked read"}
