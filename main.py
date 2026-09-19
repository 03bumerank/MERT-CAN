import os
import secrets
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_KEY = os.environ["ADMIN_KEY"]

app = FastAPI(title="Origins License Server", version="1.0.0")


def db():
    return psycopg.connect(DATABASE_URL)


def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                license_key TEXT PRIMARY KEY,
                expires_at TIMESTAMPTZ NOT NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                device_id TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)


@app.on_event("startup")
def startup():
    init_db()


def admin_auth(x_admin_key: str | None):
    if not x_admin_key or not secrets.compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(status_code=401, detail="Yetkisiz işlem.")


def new_key():
    return "ORG-" + "-".join(secrets.token_hex(2).upper() for _ in range(4))


class VerifyRequest(BaseModel):
    license_key: str
    device_id: str


class CreateRequest(BaseModel):
    days: int = 30


class LicenseRequest(BaseModel):
    license_key: str


class ExtendRequest(BaseModel):
    license_key: str
    days: int = 30


@app.get("/")
def root():
    return {"ok": True, "service": "Origins License Server"}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/verify")
def verify(data: VerifyRequest):
    key = data.license_key.strip().upper()
    device = data.device_id.strip()

    if not key or not device:
        return {"valid": False, "message": "Eksik lisans veya cihaz bilgisi."}

    with db() as con:
        row = con.execute(
            "SELECT expires_at, active, device_id FROM licenses WHERE license_key=%s",
            (key,)
        ).fetchone()

        if not row:
            return {"valid": False, "message": "Lisans bulunamadı."}

        expires_at, active, saved_device = row
        now = datetime.now(timezone.utc)

        if not active:
            return {"valid": False, "message": "Lisans pasif."}

        if now >= expires_at:
            return {"valid": False, "message": "Lisans süresi dolmuş.", "days_left": 0}

        if saved_device and saved_device != device:
            return {"valid": False, "message": "Bu lisans başka bir bilgisayara bağlı."}

        if not saved_device:
            con.execute(
                "UPDATE licenses SET device_id=%s WHERE license_key=%s",
                (device, key)
            )

        seconds_left = max(0, int((expires_at - now).total_seconds()))
        days_left = (seconds_left + 86399) // 86400

        return {
            "valid": True,
            "message": "Lisans aktif.",
            "days_left": days_left,
            "expires_at": expires_at.isoformat()
        }


@app.post("/admin/create")
def create_license(data: CreateRequest, x_admin_key: str | None = Header(default=None)):
    admin_auth(x_admin_key)

    if data.days < 1 or data.days > 3650:
        raise HTTPException(status_code=400, detail="Gün değeri 1-3650 arasında olmalı.")

    key = new_key()
    expires = datetime.now(timezone.utc) + timedelta(days=data.days)

    with db() as con:
        con.execute(
            "INSERT INTO licenses (license_key, expires_at) VALUES (%s, %s)",
            (key, expires)
        )

    return {"ok": True, "license_key": key, "days": data.days, "expires_at": expires.isoformat()}


@app.get("/admin/licenses")
def list_licenses(x_admin_key: str | None = Header(default=None)):
    admin_auth(x_admin_key)

    with db() as con:
        rows = con.execute("""
            SELECT license_key, expires_at, active, device_id, created_at
            FROM licenses
            ORDER BY created_at DESC
        """).fetchall()

    return {
        "licenses": [
            {
                "license_key": r[0],
                "expires_at": r[1].isoformat(),
                "active": r[2],
                "device_bound": bool(r[3]),
                "created_at": r[4].isoformat()
            }
            for r in rows
        ]
    }


@app.post("/admin/extend")
def extend_license(data: ExtendRequest, x_admin_key: str | None = Header(default=None)):
    admin_auth(x_admin_key)

    if data.days < 1 or data.days > 3650:
        raise HTTPException(status_code=400, detail="Gün değeri 1-3650 arasında olmalı.")

    key = data.license_key.strip().upper()
    now = datetime.now(timezone.utc)

    with db() as con:
        row = con.execute(
            "SELECT expires_at FROM licenses WHERE license_key=%s", (key,)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Lisans bulunamadı.")

        base = row[0] if row[0] > now else now
        new_expiry = base + timedelta(days=data.days)
        con.execute(
            "UPDATE licenses SET expires_at=%s WHERE license_key=%s",
            (new_expiry, key)
        )

    return {"ok": True, "expires_at": new_expiry.isoformat()}


@app.post("/admin/deactivate")
def deactivate(data: LicenseRequest, x_admin_key: str | None = Header(default=None)):
    admin_auth(x_admin_key)
    key = data.license_key.strip().upper()

    with db() as con:
        cur = con.execute("UPDATE licenses SET active=FALSE WHERE license_key=%s", (key,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Lisans bulunamadı.")

    return {"ok": True}


@app.post("/admin/activate")
def activate(data: LicenseRequest, x_admin_key: str | None = Header(default=None)):
    admin_auth(x_admin_key)
    key = data.license_key.strip().upper()

    with db() as con:
        cur = con.execute("UPDATE licenses SET active=TRUE WHERE license_key=%s", (key,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Lisans bulunamadı.")

    return {"ok": True}


@app.post("/admin/reset-device")
def reset_device(data: LicenseRequest, x_admin_key: str | None = Header(default=None)):
    admin_auth(x_admin_key)
    key = data.license_key.strip().upper()

    with db() as con:
        cur = con.execute("UPDATE licenses SET device_id=NULL WHERE license_key=%s", (key,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Lisans bulunamadı.")

    return {"ok": True}


@app.get("/public/status")
def public_license_status(license_key: str):
    license_key = license_key.strip().upper()

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT license_key, expires_at, active, device_id
                FROM licenses
                WHERE license_key = %s
                """,
                (license_key,),
            )
            row = cur.fetchone()

    if not row:
        return {
            "valid": False,
            "message": "Lisans kodu bulunamadı.",
            "days_left": 0,
            "device_bound": False,
        }

    _, expires_at, active, device_id = row
    now = datetime.now(timezone.utc)

    if not active:
        return {
            "valid": False,
            "message": "Lisans pasif durumda.",
            "days_left": 0,
            "device_bound": bool(device_id),
        }

    if expires_at <= now:
        return {
            "valid": False,
            "message": "Lisans süresi dolmuş.",
            "days_left": 0,
            "device_bound": bool(device_id),
        }

    seconds = max(0, int((expires_at - now).total_seconds()))
    days_left = (seconds + 86399) // 86400

    return {
        "valid": True,
        "message": "Lisans aktif.",
        "days_left": days_left,
        "device_bound": bool(device_id),
    }
