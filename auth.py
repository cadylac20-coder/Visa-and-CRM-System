import os
from datetime import datetime, timedelta
from jose import jwt, JWTError
import bcrypt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_db

SECRET_KEY  = os.getenv("SECRET_KEY", "visa-mkov-secret-key-change-in-production-2026")
ALGORITHM   = "HS256"
TOKEN_HOURS = 12

bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=TOKEN_HOURS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── Roles ──────────────────────────────────────────────────────────────────────
# superadmin : full access, can create/edit/remove staff and assign roles
# sales      : leads, follow-ups, clients, messaging
# visa_staff : applications, documents, checklists, hotels, invoices, payments, fee structure
# staff      : legacy role, treated like superadmin for backward compatibility
ALL_ROLES = ("superadmin", "staff", "sales", "visa_staff")


# ── Dependency: require admin JWT (any staff role) ────────────────────────────
def require_admin(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_token(creds.credentials)
    if payload.get("role") not in ALL_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload


# ── Dependency: require superadmin (for staff management) ────────────────────
def require_superadmin(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_token(creds.credentials)
    if payload.get("role") not in ("superadmin", "staff"):
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return payload


# ── Factory: require one of a set of roles ────────────────────────────────────
def require_roles(*roles):
    """
    Usage: Depends(require_roles('superadmin', 'visa_staff'))
    superadmin/staff always pass regardless of which roles are listed.
    """
    def checker(creds: HTTPAuthorizationCredentials = Depends(bearer)):
        if not creds:
            raise HTTPException(status_code=401, detail="Authentication required")
        payload = decode_token(creds.credentials)
        role = payload.get("role")
        if role in ("superadmin", "staff"):
            return payload
        if role not in roles:
            raise HTTPException(status_code=403, detail=f"Requires one of: {', '.join(roles)}")
        return payload
    return checker


# ── Dependency: require client JWT ───────────────────────────────────────────
def require_client(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_token(creds.credentials)
    if payload.get("role") != "client":
        raise HTTPException(status_code=403, detail="Client access required")
    return payload


# ── Login helpers ─────────────────────────────────────────────────────────────
def admin_login(email: str, password: str) -> dict:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM admin_users WHERE email=? AND active=1", (email,)
    ).fetchone()
    conn.close()
    if not row or not verify_password(password, row["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token({"sub": row["email"], "role": row["role"], "name": row["name"], "id": row["id"]})
    return {"token": token, "name": row["name"], "role": row["role"], "id": row["id"]}


def client_login(email: str, password: str) -> dict:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM clients WHERE email=?", (email,)
    ).fetchone()
    conn.close()
    if not row or not verify_password(password, row["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token({"sub": row["email"], "role": "client", "name": row["name"], "id": row["id"]})
    return {"token": token, "name": row["name"], "client_id": row["id"]}