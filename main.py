"""MKOV Visa & CRM System - Enhanced with new roles, activity tracking, and IST timezone"""
from fastapi import FastAPI, Depends, Form, File, UploadFile, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import os
import json
import sqlite3
from datetime import datetime, timedelta
import pytz
import bcrypt
from database import get_db, init_db, now_ist, now_ist_str, IST

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="MKOV Visa System", version="2.0.0", docs_url="/docs")

STATUS_PROGRESS = {
    "pending": 10, "docs_received": 35, "review": 55,
    "submitted": 75, "approved": 100, "rejected": 0,
}

# ── Auth Helpers ──────────────────────────────────────────────────────────────
def get_admin_session(token: str = None):
    if not token:
        return None
    conn = get_db()
    admin = conn.execute("SELECT * FROM admin_users WHERE id = ?", (token,)).fetchone()
    conn.close()
    return admin

def log_staff_activity(staff_id: int, staff_name: str, action: str, detail: str = ""):
    """Log staff activity permanently."""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO staff_activity (staff_id, staff_name, action, detail, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (staff_id, staff_name, action, detail, now_ist_str("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def log_change(app_id: str, actor_id: int, actor_name: str, action: str, detail: str, changes: str = ""):
    """Log permanent changes with before/after tracking."""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO activity_log (app_id, actor_id, actor_name, action, detail, changes, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (app_id, actor_id, actor_name, action, detail, changes, now_ist_str("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# ── Schemas ───────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str

class StaffActivityRequest(BaseModel):
    action: str
    detail: Optional[str] = ""

class TeamMessageRequest(BaseModel):
    message: str
    recipient_id: Optional[int] = None  # None = broadcast to all
    is_pinned: bool = False

class StaffDetailRequest(BaseModel):
    staff_id: int  # For super admin to view another staff member

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/")
def root(): 
    return {"status": "online", "service": "MKOV Visa System v2.0.0", "timezone": "IST"}

@app.get("/health")
def health(): 
    return {"status": "ok", "timestamp": now_ist_str()}

@app.get("/admin", response_class=HTMLResponse)
def serve_admin():
    with open(os.path.join(STATIC_DIR, "admin.html")) as f:
        return f.read()

@app.post("/auth/admin/login")
def login_admin(data: LoginRequest):
    """Admin login with IST timestamp."""
    conn = get_db()
    admin = conn.execute("SELECT * FROM admin_users WHERE email = ?", (data.email,)).fetchone()
    conn.close()
    
    if not admin or not bcrypt.checkpw(data.password.encode(), admin['password'].encode()):
        log_staff_activity(0, data.email, "login_failed", "Invalid credentials")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Update last login
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE admin_users SET last_login = ?, session_start = ? WHERE id = ?",
        (now_ist_str("%Y-%m-%d %H:%M:%S"), now_ist_str("%Y-%m-%d %H:%M:%S"), admin['id'])
    )
    conn.commit()
    conn.close()
    
    log_staff_activity(admin['id'], admin['name'], "login", f"Role: {admin['role']}")
    
    return {
        "success": True,
        "admin_id": admin['id'],
        "name": admin['name'],
        "email": admin['email'],
        "role": admin['role'],
        "timestamp": now_ist_str()
    }

@app.post("/admin/team-message")
def send_team_message(data: TeamMessageRequest, admin_id: int = Query(...)):
    """Super admin can message team members or broadcast."""
    conn = get_db()
    sender = conn.execute("SELECT * FROM admin_users WHERE id = ?", (admin_id,)).fetchone()
    
    if not sender or sender['role'] != 'superadmin':
        conn.close()
        raise HTTPException(status_code=403, detail="Only super admin can send team messages")
    
    c = conn.cursor()
    c.execute("""
        INSERT INTO team_chat_messages (sender_id, sender_name, sender_role, recipient_id, message, is_pinned, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        admin_id, sender['name'], sender['role'],
        data.recipient_id, data.message, 1 if data.is_pinned else 0,
        now_ist_str("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    msg_id = c.lastrowid
    conn.close()
    
    recipient_name = "Team" if data.recipient_id is None else f"Staff Member {data.recipient_id}"
    log_staff_activity(admin_id, sender['name'], "message_sent", f"To: {recipient_name}, Pinned: {data.is_pinned}")
    
    return {"success": True, "message_id": msg_id, "timestamp": now_ist_str()}

@app.get("/admin/team-messages")
def get_team_messages(admin_id: int = Query(...), recipient_only: bool = False):
    """Get team messages. Super admin can see all, others see their messages."""
    conn = get_db()
    admin = conn.execute("SELECT * FROM admin_users WHERE id = ?", (admin_id,)).fetchone()
    
    if admin['role'] == 'superadmin':
        msgs = conn.execute("""
            SELECT * FROM team_chat_messages 
            ORDER BY created_at DESC LIMIT 100
        """).fetchall()
    else:
        msgs = conn.execute("""
            SELECT * FROM team_chat_messages 
            WHERE recipient_id IS NULL OR recipient_id = ?
            ORDER BY created_at DESC LIMIT 100
        """, (admin_id,)).fetchall()
    
    conn.close()
    return [{"id": m['id'], "sender": m['sender_name'], "role": m['sender_role'], "message": m['message'], 
             "pinned": m['is_pinned'], "timestamp": m['created_at']} for m in msgs]

@app.get("/admin/staff/{staff_id}/activity")
def get_staff_activity(staff_id: int, admin_id: int = Query(...), days: int = Query(7)):
    """Super admin can view any staff member's activity log."""
    conn = get_db()
    viewer = conn.execute("SELECT * FROM admin_users WHERE id = ?", (admin_id,)).fetchone()
    
    if not viewer or viewer['role'] != 'superadmin':
        conn.close()
        raise HTTPException(status_code=403, detail="Only super admin can view staff activity")
    
    activities = conn.execute("""
        SELECT * FROM staff_activity 
        WHERE staff_id = ? AND timestamp > datetime('now', '-' || ? || ' days')
        ORDER BY timestamp DESC
    """, (staff_id, days)).fetchall()
    
    staff = conn.execute("SELECT * FROM admin_users WHERE id = ?", (staff_id,)).fetchone()
    conn.close()
    
    total_minutes = 0
    if staff['session_start'] and staff['session_end']:
        start = datetime.fromisoformat(staff['session_start'])
        end = datetime.fromisoformat(staff['session_end'])
        total_minutes = int((end - start).total_seconds() / 60)
    
    return {
        "staff_name": staff['name'],
        "role": staff['role'],
        "last_login": staff['last_login'],
        "session_duration_minutes": total_minutes,
        "activities": [
            {
                "action": a['action'],
                "detail": a['detail'],
                "timestamp": a['timestamp']
            } for a in activities
        ]
    }

@app.post("/admin/staff")
def create_staff(email: str, name: str, password: str, role: str, admin_id: int = Query(...)):
    """Super admin creates new staff with roles: sales_admin, visa_admin, sales, visa_staff."""
    conn = get_db()
    creator = conn.execute("SELECT * FROM admin_users WHERE id = ?", (admin_id,)).fetchone()
    
    if not creator or creator['role'] != 'superadmin':
        conn.close()
        raise HTTPException(status_code=403, detail="Only super admin can create staff")
    
    if role not in ['superadmin', 'sales_admin', 'visa_admin', 'sales', 'visa_staff', 'staff']:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    c = conn.cursor()
    
    try:
        c.execute("""
            INSERT INTO admin_users (email, name, password, role, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (email, name, pwd_hash, role, now_ist_str("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        staff_id = c.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Email already exists")
    
    conn.close()
    log_staff_activity(admin_id, creator['name'], "staff_created", f"Name: {name}, Role: {role}")
    
    return {"success": True, "staff_id": staff_id, "message": f"Staff {role} created", "timestamp": now_ist_str()}

@app.get("/backend-check")
def backend_check():
    """Check backend and view API documentation."""
    return {
        "status": "Backend is running",
        "timezone": "IST (Asia/Kolkata)",
        "api_docs": "https://visa-automation-3hgo.onrender.com/docs",
        "current_time_ist": now_ist_str(),
        "database": "SQLite with permanent change logging",
        "changelog_access": "View /docs -> /admin/staff/{staff_id}/activity endpoint",
        "features": {
            "roles": ["superadmin", "sales_admin", "visa_admin", "sales", "visa_staff"],
            "activity_tracking": "All changes logged with timestamp and user info",
            "team_messaging": "Super admin can message and ping team members",
            "timezone": "All timestamps in IST"
        }
    }

# Mount static files
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    init_db()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
