#!/usr/bin/env python3
"""CreatorWatch License Server — M1.

Tiny cloud service for accounts + license keys.
The desktop app itself stays 100% local; on startup it calls
POST /api/licenses/validate and unlocks when the key is valid.

Tables (SQLite, created automatically):
  users(id, email UNIQUE, password_hash, created_at)
  licenses(id, user_id FK, key_hash UNIQUE, key_prefix, plan,
           max_machines, expires_at, revoked, created_at)
  activations(id, license_id FK, machine_id, activated_at,
              UNIQUE(license_id, machine_id))

Dev run:
  python app.py            # http://127.0.0.1:5001

Env:
  LICENSE_DB             path to sqlite file (default ./licenses.db)
  LICENSE_ADMIN_TOKEN    token for POST /api/admin/licenses (default "change-me")
  LICENSE_SESSION_SECRET flask secret (default: random per boot)
  HOST / PORT            default 127.0.0.1 / 5001
"""

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request, session, render_template, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("LICENSE_DB", os.path.join(APP_ROOT, "licenses.db"))
ADMIN_TOKEN = os.environ.get("LICENSE_ADMIN_TOKEN", "change-me")
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "5001"))

app = Flask(__name__)
app.secret_key = os.environ.get("LICENSE_SESSION_SECRET", secrets.token_hex(32))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS licenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  key_hash TEXT UNIQUE NOT NULL,
  key_prefix TEXT NOT NULL,
  plan TEXT NOT NULL DEFAULT 'pro',
  max_machines INTEGER NOT NULL DEFAULT 2,
  expires_at TEXT,
  revoked INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  license_id INTEGER NOT NULL REFERENCES licenses(id),
  machine_id TEXT NOT NULL,
  activated_at TEXT NOT NULL,
  UNIQUE(license_id, machine_id)
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def _close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    db.commit()
    db.close()


def new_key():
    # CW-XXXX-XXXX-XXXX-XXXX  (16 hex chars in human-typable groups)
    raw = secrets.token_hex(8).upper()
    return "CW-" + "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def key_hash(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    row = get_db().execute(
        "SELECT id, email, created_at FROM users WHERE id = ?", (uid,)).fetchone()
    return dict(row) if row else None


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **k):
        if not current_user():
            return jsonify(error="login required"), 401
        return fn(*a, **k)
    return wrapper


def login_required_page(fn):
    """HTML pages: login nahi to /login par bhejo (API wali 401 nahi)."""
    @wraps(fn)
    def wrapper(*a, **k):
        if not current_user():
            return redirect(url_for("login_page", next=request.path))
        return fn(*a, **k)
    return wrapper


# ---------------- CSRF (sirf browser forms ke liye; desktop API untouched) ----------------

def _csrf_token():
    tok = session.get("_csrf")
    if not tok:
        tok = secrets.token_hex(16)
        session["_csrf"] = tok
    return tok


def _check_csrf():
    want = session.get("_csrf")
    got = request.form.get("_csrf", "")
    return bool(want) and secrets.compare_digest(got, want)


@app.context_processor
def _inject_tpl():
    return {"csrf_token": _csrf_token, "user": current_user()}


def _safe_next(url):
    return url if url and url.startswith("/") and not url.startswith("//") else None


def require_admin(fn):
    @wraps(fn)
    def wrapper(*a, **k):
        if request.headers.get("X-Admin-Token") != ADMIN_TOKEN:
            return jsonify(error="unauthorized"), 401
        return fn(*a, **k)
    return wrapper


@app.get("/api/health")
def health():
    return jsonify(service="creatorwatch-license-server", version="0.2.0",
                   endpoints=["POST /api/signup", "POST /api/login",
                              "GET /api/me", "POST /api/admin/licenses",
                              "POST /api/licenses/validate",
                              "POST /api/licenses/deactivate"])


@app.get("/")
def index():
    """Public landing page — yehi cw.raoshahzaib.site par khulega."""
    return render_template("index.html")


# ---------------- accounts (core logic: API + HTML dono istemal karte hain) ----------------

def _valid_email(email):
    return "@" in email and "." in email.split("@")[-1]


def _do_signup(email, password):
    """Returns (user_id, error). error None = kamyab."""
    email = (email or "").strip().lower()
    password = password or ""
    if not _valid_email(email):
        return None, "valid email required"
    if len(password) < 8:
        return None, "password must be at least 8 characters"
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users(email, password_hash, created_at) VALUES (?,?,?)",
            (email, generate_password_hash(password), _now()))
        db.commit()
    except sqlite3.IntegrityError:
        return None, "email already registered"
    return cur.lastrowid, None


def _do_login(email, password):
    """Returns (user_dict, error)."""
    email = (email or "").strip().lower()
    row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password or ""):
        return None, "invalid email or password"
    return {"id": row["id"], "email": row["email"]}, None


def _user_with_licenses(uid):
    db = get_db()
    user = db.execute(
        "SELECT id, email, created_at FROM users WHERE id = ?", (uid,)).fetchone()
    if not user:
        return None
    rows = db.execute(
        "SELECT key_prefix, plan, max_machines, expires_at, revoked, created_at,"
        " (SELECT COUNT(*) FROM activations a WHERE a.license_id = licenses.id) AS machines"
        " FROM licenses WHERE user_id = ? ORDER BY id DESC", (uid,)).fetchall()
    u = dict(user)
    u["licenses"] = [dict(r) for r in rows]
    return u


@app.post("/api/signup")
def signup():
    data = request.get_json(force=True, silent=True) or {}
    uid, err = _do_signup(data.get("email"), data.get("password"))
    if err:
        code = 409 if err == "email already registered" else 400
        return jsonify(error=err), code
    session["uid"] = uid
    return jsonify(id=uid, email=(data.get("email") or "").strip().lower()), 201


@app.post("/api/login")
def login():
    data = request.get_json(force=True, silent=True) or {}
    user, err = _do_login(data.get("email"), data.get("password"))
    if err:
        return jsonify(error=err), 401
    session["uid"] = user["id"]
    return jsonify(id=user["id"], email=user["email"])


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
@login_required
def me():
    return jsonify(_user_with_licenses(session["uid"]))


# ---------------- web pages ----------------

@app.route("/signup", methods=["GET", "POST"])
def signup_page():
    if current_user():
        return redirect(url_for("dashboard"))
    err, email = "", ""
    if request.method == "POST":
        email = request.form.get("email", "")
        if not _check_csrf():
            err = "session expired — page reload kar ke dobara try karo"
        else:
            uid, err = _do_signup(email, request.form.get("password", ""))
            if uid:
                session["uid"] = uid
                return redirect(url_for("dashboard"))
    return render_template("signup.html", error=err, email=email)


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if current_user():
        return redirect(url_for("dashboard"))
    err, email = "", ""
    nxt = _safe_next(request.args.get("next") or request.form.get("next", ""))
    if request.method == "POST":
        email = request.form.get("email", "")
        if not _check_csrf():
            err = "session expired — page reload kar ke dobara try karo"
        else:
            user, err = _do_login(email, request.form.get("password", ""))
            if user:
                session["uid"] = user["id"]
                return redirect(nxt or url_for("dashboard"))
    return render_template("login.html", error=err, email=email,
                           next=request.args.get("next", ""))


@app.get("/logout")
def logout_page():
    session.clear()
    return redirect(url_for("index"))


@app.get("/dashboard")
@login_required_page
def dashboard():
    return render_template("dashboard.html",
                           user=_user_with_licenses(session["uid"]))


# ---------------- licenses (admin) ----------------

@app.post("/api/admin/licenses")
@require_admin
def create_license():
    """Create a license key for a user. M1: manual/admin. M3: Binance Pay webhook."""
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    plan = (data.get("plan") or "pro").strip()
    max_machines = int(data.get("max_machines", 2))
    days = data.get("days", 365)  # 0/None -> lifetime
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if not user:
        return jsonify(error="user not found (signup first)"), 404
    key = new_key()
    expires_at = None
    if days:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=int(days))).isoformat()
    cur = db.execute(
        "INSERT INTO licenses(user_id, key_hash, key_prefix, plan, max_machines,"
        " expires_at, created_at) VALUES (?,?,?,?,?,?,?)",
        (user["id"], key_hash(key), key[:7], plan, max_machines, expires_at, _now()))
    db.commit()
    # Full key is returned ONCE here — only its hash is stored.
    return jsonify(license_id=cur.lastrowid, key=key, plan=plan,
                   max_machines=max_machines, expires_at=expires_at), 201


# ---------------- validation (called by the desktop app) ----------------

def _license_status(lic):
    if lic["revoked"]:
        return False, "license revoked"
    if lic["expires_at"]:
        exp = datetime.fromisoformat(lic["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return False, "license expired"
    return True, "ok"


@app.post("/api/licenses/validate")
def validate():
    data = request.get_json(force=True, silent=True) or {}
    key = (data.get("key") or "").strip().upper()
    machine_id = (data.get("machine_id") or "").strip()
    if not key or not machine_id:
        return jsonify(valid=False, error="key and machine_id required"), 400
    db = get_db()
    lic = db.execute(
        "SELECT l.*, u.email FROM licenses l JOIN users u ON u.id = l.user_id"
        " WHERE l.key_hash = ?", (key_hash(key),)).fetchone()
    if not lic:
        return jsonify(valid=False, error="unknown key"), 404
    ok, reason = _license_status(lic)
    if not ok:
        return jsonify(valid=False, error=reason), 403
    # Record this machine; a machine re-validating costs no extra seat.
    db.execute("INSERT OR IGNORE INTO activations(license_id, machine_id, activated_at)"
               " VALUES (?,?,?)", (lic["id"], machine_id, _now()))
    db.commit()
    used = db.execute("SELECT COUNT(*) c FROM activations WHERE license_id = ?",
                      (lic["id"],)).fetchone()["c"]
    if used > lic["max_machines"]:
        # New machine over the seat limit: roll back its activation, reject.
        db.execute("DELETE FROM activations WHERE license_id = ? AND machine_id = ?",
                   (lic["id"], machine_id))
        db.commit()
        return jsonify(valid=False,
                       error="seat limit reached — deactivate another machine first"), 403
    return jsonify(valid=True, email=lic["email"], plan=lic["plan"],
                   expires_at=lic["expires_at"], max_machines=lic["max_machines"],
                   machines_used=used)


@app.post("/api/licenses/deactivate")
def deactivate():
    """Free a seat, e.g. user reinstalls Windows or switches machine."""
    data = request.get_json(force=True, silent=True) or {}
    key = (data.get("key") or "").strip().upper()
    machine_id = (data.get("machine_id") or "").strip()
    if not key or not machine_id:
        return jsonify(error="key and machine_id required"), 400
    db = get_db()
    lic = db.execute("SELECT id FROM licenses WHERE key_hash = ?",
                     (key_hash(key),)).fetchone()
    if not lic:
        return jsonify(error="unknown key"), 404
    db.execute("DELETE FROM activations WHERE license_id = ? AND machine_id = ?",
               (lic["id"], machine_id))
    db.commit()
    return jsonify(ok=True)


if __name__ == "__main__":
    init_db()
    app.run(host=HOST, port=PORT)
