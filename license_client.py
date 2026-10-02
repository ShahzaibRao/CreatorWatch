"""License client for the CreatorWatch desktop app (M2).

Talks to the license server (license-server/app.py). Pure stdlib —
no new dependencies.

Local cache lives in the app's SQLite settings table:
  license_key         the activated key (stored only after server says valid)
  license_email       account email from server
  license_plan        plan name from server
  license_expires_at  ISO timestamp or ""
  license_last_ok     ISO timestamp of last successful server validation
  license_last_check  ISO timestamp of last validation attempt

Policy:
  - First activation MUST be online (server must say valid).
  - Afterwards the server is re-checked at most once per RECHECK_HOURS.
  - If the server is unreachable, a cached validation younger than
    GRACE_DAYS keeps working (offline grace period).
"""

import hashlib
import json
import os
import platform
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timedelta, timezone

SERVER_URL = os.environ.get("LICENSE_SERVER_URL", "http://127.0.0.1:5001").rstrip("/")
TIMEOUT = 8
RECHECK_HOURS = 1
GRACE_DAYS = 7


def machine_id():
    raw = f"{platform.node()}|{uuid.getnode():x}|{platform.system()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _now():
    return datetime.now(timezone.utc)


def _post(path, payload):
    req = urllib.request.Request(
        SERVER_URL + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = {"error": f"server error {e.code}"}
        return e.code, body
    except Exception as e:
        return None, {"error": f"unreachable: {e}"}


def cached_status(db):
    """What we know locally, without contacting the server."""
    return {
        "key": db.get_setting("license_key", "") or "",
        "email": db.get_setting("license_email", "") or "",
        "plan": db.get_setting("license_plan", "") or "",
        "expires_at": db.get_setting("license_expires_at", "") or "",
        "last_ok": db.get_setting("license_last_ok", "") or "",
        "machines_used": db.get_setting("license_machines_used", "") or "",
        "max_machines": db.get_setting("license_max_machines", "") or "",
    }


def _within_grace(last_ok):
    if not last_ok:
        return False
    try:
        ts = datetime.fromisoformat(last_ok)
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return _now() - ts < timedelta(days=GRACE_DAYS)


def is_activated(db):
    """(ok, reason). Called on every request via before_request — cheap:
    hits the server at most once per RECHECK_HOURS, otherwise trusts cache."""
    key = (db.get_setting("license_key", "") or "").strip()
    if not key:
        return False, "no_key"
    last_check = db.get_setting("license_last_check", "") or ""
    last_ok = db.get_setting("license_last_ok", "") or ""
    recent = False
    if last_check:
        try:
            ts = datetime.fromisoformat(last_check)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            recent = _now() - ts < timedelta(hours=RECHECK_HOURS)
        except ValueError:
            recent = False
    if recent and last_ok:
        return True, "cached"
    status, data = _post("/api/licenses/validate",
                         {"key": key, "machine_id": machine_id()})
    now_iso = _now().isoformat()
    if data.get("valid"):
        db.set_setting("license_last_check", now_iso)
        db.set_setting("license_last_ok", now_iso)
        db.set_setting("license_email", data.get("email", ""))
        db.set_setting("license_plan", data.get("plan", ""))
        db.set_setting("license_expires_at", data.get("expires_at") or "")
        db.set_setting("license_machines_used", data.get("machines_used", ""))
        db.set_setting("license_max_machines", data.get("max_machines", ""))
        return True, "ok"
    if status is None:
        # Server unreachable — offline grace period.
        db.set_setting("license_last_check", now_iso)
        if _within_grace(last_ok):
            return True, "offline_grace"
        return False, "server unreachable and grace period expired"
    # Server says no (unknown / revoked / expired / seat limit).
    db.set_setting("license_last_check", now_iso)
    return False, data.get("error", "license invalid")


def activate(db, key):
    """First activation — must be online. Returns (True, info) / (False, error)."""
    key = (key or "").strip().upper()
    if not key:
        return False, "Key likho pehle."
    status, data = _post("/api/licenses/validate",
                         {"key": key, "machine_id": machine_id()})
    if status is None:
        return False, "License server se connect nahi ho saka. Internet check karo."
    if not data.get("valid"):
        return False, data.get("error", "Key ghalat hai.")
    now_iso = _now().isoformat()
    db.set_setting("license_key", key)
    db.set_setting("license_last_check", now_iso)
    db.set_setting("license_last_ok", now_iso)
    db.set_setting("license_email", data.get("email", ""))
    db.set_setting("license_plan", data.get("plan", ""))
    db.set_setting("license_expires_at", data.get("expires_at") or "")
    db.set_setting("license_machines_used", data.get("machines_used", ""))
    db.set_setting("license_max_machines", data.get("max_machines", ""))
    return True, data


def deactivate(db):
    """Free the seat on the server and forget the local key."""
    key = (db.get_setting("license_key", "") or "").strip()
    if key:
        _post("/api/licenses/deactivate", {"key": key, "machine_id": machine_id()})
    for k in ("license_key", "license_email", "license_plan",
              "license_expires_at", "license_last_ok", "license_last_check",
              "license_machines_used", "license_max_machines"):
        db.set_setting(k, "")
    return True
