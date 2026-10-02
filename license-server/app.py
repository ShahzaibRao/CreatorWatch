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

import base64
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
# Koi domain hardcode nahi — jo clone kare apne domain se chalaye:
#   SITE_DOMAIN=cw.raoshahzaib.site SITE_NAME=CreatorWatch python app.py
SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "").strip().rstrip("/")
SITE_NAME = os.environ.get("SITE_NAME", "").strip() or "CreatorWatch"

app = Flask(__name__)
app.secret_key = os.environ.get("LICENSE_SESSION_SECRET") or secrets.token_hex(32)

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


_schema_ready = False


def get_db():
    global _schema_ready
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    if not _schema_ready:
        # gunicorn jese servers me __main__ nahi chalta — pehli request par schema pakka karo
        g.db.executescript(SCHEMA)
        _migrate_schema(g.db)
        _schema_ready = True
    return g.db


@app.teardown_appcontext
def _close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    _migrate_schema(db)
    db.commit()
    db.close()


def _migrate_schema(db):
    """Purani DB me naye columns (M3a: revenue tracking, key reveal)."""
    cols = {r[1] for r in db.execute("PRAGMA table_info(licenses)").fetchall()}
    for col, ddl in (("amount_cents", "ADD COLUMN amount_cents INTEGER NOT NULL DEFAULT 0"),
                     ("currency", "ADD COLUMN currency TEXT NOT NULL DEFAULT 'USD'"),
                     ("key_enc", "ADD COLUMN key_enc TEXT")):
        if col not in cols:
            try:
                db.execute(f"ALTER TABLE licenses {ddl}")
            except sqlite3.OperationalError:
                pass  # concurrent first request ne pehle add kar diya
    db.commit()


def _key_cipher():
    """Full key encrypted-at-rest (user dashboard par Reveal ke liye).
    Secret: LICENSE_KEY_SECRET env; nahi to DB ke sath .key_secret file me
    (0600). DB leak bhi ho to secret ke baghair keys nahi nikalteen."""
    from cryptography.fernet import Fernet
    secret = os.environ.get("LICENSE_KEY_SECRET")
    if not secret:
        p = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), ".key_secret")
        try:
            if os.path.exists(p):
                with open(p) as f:
                    secret = f.read().strip()
            else:
                secret = secrets.token_hex(32)
                with open(p, "w") as f:
                    f.write(secret)
                os.chmod(p, 0o600)
        except OSError:
            secret = secrets.token_hex(32)
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_key(key):
    try:
        return _key_cipher().encrypt(key.encode("utf-8")).decode("utf-8")
    except Exception:
        return None


def _decrypt_key(key_enc):
    try:
        return _key_cipher().decrypt(key_enc.encode("utf-8")).decode("utf-8")
    except Exception:
        return None


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
    return {"csrf_token": _csrf_token, "user": current_user(),
            "site_domain": SITE_DOMAIN, "site_name": SITE_NAME}


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
    """Public landing page."""
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
        "SELECT id, key_prefix, plan, max_machines, expires_at, revoked, created_at,"
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


@app.get("/api/my/licenses/<int:lid>/key")
@login_required
def my_license_key(lid):
    """Apni key wapas dekho (encrypted-at-rest se decrypt). Sirf apni license."""
    row = get_db().execute(
        "SELECT key_enc FROM licenses WHERE id = ? AND user_id = ? AND revoked = 0",
        (lid, session["uid"])).fetchone()
    if not row or not row["key_enc"]:
        return jsonify(error="key not available — admin se regenerate karwao"), 404
    key = _decrypt_key(row["key_enc"])
    if not key:
        return jsonify(error="decrypt failed"), 500
    return jsonify(key=key)


@app.get("/dashboard")
@login_required_page
def dashboard():
    return render_template("dashboard.html",
                           user=_user_with_licenses(session["uid"]))


# ---------------- admin panel ----------------

def _fmt_money(cents, currency="USD"):
    try:
        v = (cents or 0) / 100
    except TypeError:
        v = 0
    sym = {"USD": "$", "EUR": "€", "PKR": "Rs"}.get((currency or "USD").upper(), (currency or "") + " ")
    return f"{sym}{v:,.2f}"


def admin_required_page(fn):
    @wraps(fn)
    def wrapper(*a, **k):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return fn(*a, **k)
    return wrapper


@app.context_processor
def _inject_admin():
    return {"is_admin": bool(session.get("is_admin")), "fmt_money": _fmt_money}


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_home"))
    err = ""
    nxt = _safe_next(request.args.get("next") or request.form.get("next", ""))
    if request.method == "POST":
        if not _check_csrf():
            err = "session expired — reload and try again"
        elif secrets.compare_digest(request.form.get("token", ""), ADMIN_TOKEN):
            session["is_admin"] = True
            return redirect(nxt or url_for("admin_home"))
        else:
            err = "wrong admin token"
    return render_template("admin_login.html", error=err,
                           next=request.args.get("next", ""))


@app.get("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


def _admin_stats():
    db = get_db()
    users = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    licenses = db.execute("SELECT COUNT(*) c FROM licenses WHERE revoked = 0").fetchone()["c"]
    devices = db.execute("SELECT COUNT(*) c FROM activations").fetchone()["c"]
    revenue = db.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) s FROM licenses WHERE revoked = 0").fetchone()["s"]
    return {"users": users, "licenses": licenses, "devices": devices,
            "revenue_cents": revenue}


@app.get("/admin")
@admin_required_page
def admin_home():
    db = get_db()
    licenses = db.execute(
        "SELECT l.id, l.key_prefix, l.plan, l.max_machines, l.expires_at, l.revoked,"
        " l.amount_cents, l.currency, l.created_at, u.email,"
        " (SELECT COUNT(*) FROM activations a WHERE a.license_id = l.id) AS machines"
        " FROM licenses l JOIN users u ON u.id = l.user_id"
        " ORDER BY l.id DESC").fetchall()
    users = db.execute(
        "SELECT u.id, u.email, u.created_at,"
        " (SELECT COUNT(*) FROM licenses l WHERE l.user_id = u.id) AS licenses"
        " FROM users u ORDER BY u.id DESC").fetchall()
    devices = db.execute(
        "SELECT a.license_id, a.machine_id, a.activated_at, l.key_prefix, u.email"
        " FROM activations a JOIN licenses l ON l.id = a.license_id"
        " JOIN users u ON u.id = l.user_id"
        " ORDER BY a.activated_at DESC LIMIT 200").fetchall()
    return render_template("admin.html", stats=_admin_stats(),
                           licenses=[dict(r) for r in licenses],
                           users=[dict(r) for r in users],
                           devices=[dict(r) for r in devices],
                           new_key=request.args.get("new_key", ""),
                           msg=request.args.get("msg", ""))


def _dollars_to_cents(s):
    try:
        return int(round(float(s or 0) * 100))
    except (TypeError, ValueError):
        return 0


@app.post("/admin/licenses/create")
@admin_required_page
def admin_license_create():
    if not _check_csrf():
        return redirect(url_for("admin_home", msg="CSRF fail"))
    days = request.form.get("days", "").strip()
    lic, err = _do_create_license(
        request.form.get("email", ""), request.form.get("plan", "pro"),
        request.form.get("max_machines", 2), int(days) if days else 0,
        _dollars_to_cents(request.form.get("amount", "0")),
        request.form.get("currency", "USD"))
    if err:
        return redirect(url_for("admin_home", msg="Error: " + err))
    # Full key sirf abhi dikhao — DB me sirf hash hai, dobara nahi milegi!
    return redirect(url_for("admin_home", new_key=lic["key"],
                            msg="License created for " + request.form.get("email", "")))


@app.post("/admin/licenses/<int:lid>/revoke")
@admin_required_page
def admin_license_revoke(lid):
    if not _check_csrf():
        return redirect(url_for("admin_home", msg="CSRF fail"))
    db = get_db()
    db.execute("UPDATE licenses SET revoked = 1 - revoked WHERE id = ?", (lid,))
    db.commit()
    return redirect(url_for("admin_home", msg="License updated"))


@app.post("/admin/licenses/<int:lid>/regenerate")
@admin_required_page
def admin_license_regenerate(lid):
    """Nayi key — purani foran invalid. Key kho jaye ya leak ho jaye to."""
    if not _check_csrf():
        return redirect(url_for("admin_home", msg="CSRF fail"))
    db = get_db()
    lic = db.execute("SELECT id FROM licenses WHERE id = ?", (lid,)).fetchone()
    if not lic:
        return redirect(url_for("admin_home", msg="License not found"))
    key = new_key()
    db.execute("UPDATE licenses SET key_hash = ?, key_prefix = ?, key_enc = ? WHERE id = ?",
               (key_hash(key), key[:7], _encrypt_key(key), lid))
    db.commit()
    return redirect(url_for("admin_home", new_key=key,
                            msg="Nayi key ban gayi — PURANI key ab kaam nahi karegi. Copy kar lo!"))


@app.post("/admin/licenses/<int:lid>/delete")
@admin_required_page
def admin_license_delete(lid):
    if not _check_csrf():
        return redirect(url_for("admin_home", msg="CSRF fail"))
    db = get_db()
    db.execute("DELETE FROM activations WHERE license_id = ?", (lid,))
    db.execute("DELETE FROM licenses WHERE id = ?", (lid,))
    db.commit()
    return redirect(url_for("admin_home", msg="License deleted"))


@app.route("/admin/licenses/<int:lid>/edit", methods=["GET", "POST"])
@admin_required_page
def admin_license_edit(lid):
    db = get_db()
    lic = db.execute(
        "SELECT l.*, u.email FROM licenses l JOIN users u ON u.id = l.user_id"
        " WHERE l.id = ?", (lid,)).fetchone()
    if not lic:
        return redirect(url_for("admin_home", msg="License not found"))
    err = ""
    if request.method == "POST":
        if not _check_csrf():
            err = "session expired — reload and try again"
        else:
            exp = (request.form.get("expires_at") or "").strip()
            expires_at = None
            if exp:
                try:
                    expires_at = datetime.fromisoformat(exp).replace(
                        tzinfo=timezone.utc).isoformat()
                except ValueError:
                    err = "expiry date format ghalat hai (YYYY-MM-DD)"
            if not err:
                try:
                    max_m = int(request.form.get("max_machines", 2))
                except (TypeError, ValueError):
                    err = "max machines number hona chahiye"
            if not err:
                db.execute(
                    "UPDATE licenses SET plan = ?, max_machines = ?, expires_at = ?,"
                    " amount_cents = ?, currency = ? WHERE id = ?",
                    (request.form.get("plan", "pro").strip() or "pro", max_m,
                     expires_at, _dollars_to_cents(request.form.get("amount", "0")),
                     (request.form.get("currency", "USD") or "USD").upper(), lid))
                db.commit()
                return redirect(url_for("admin_home", msg="License updated"))
    lic = dict(lic)
    lic["expires_date"] = (lic["expires_at"] or "")[:10]
    lic["amount"] = "%.2f" % ((lic["amount_cents"] or 0) / 100)
    return render_template("admin_license_edit.html", lic=lic, error=err)


@app.post("/admin/activations/deactivate")
@admin_required_page
def admin_device_deactivate():
    if not _check_csrf():
        return redirect(url_for("admin_home", msg="CSRF fail"))
    db = get_db()
    db.execute("DELETE FROM activations WHERE license_id = ? AND machine_id = ?",
               (request.form.get("license_id"), request.form.get("machine_id")))
    db.commit()
    return redirect(url_for("admin_home", msg="Device deactivated — seat free"))


# ---------------- licenses (admin) ----------------

def _do_create_license(email, plan="pro", max_machines=2, days=365,
                       amount_cents=0, currency="USD"):
    """Returns (key_dict, error). Full key sirf ek dafa return hoti hai."""
    email = (email or "").strip().lower()
    if not _valid_email(email):
        return None, "valid email required"
    try:
        max_machines = int(max_machines)
    except (TypeError, ValueError):
        return None, "max_machines must be a number"
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if not user:
        return None, "user not found (signup first)"
    key = new_key()
    expires_at = None
    if days:
        try:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=int(days))).isoformat()
        except (TypeError, ValueError):
            return None, "days must be a number"
    cur = db.execute(
        "INSERT INTO licenses(user_id, key_hash, key_prefix, plan, max_machines,"
        " expires_at, amount_cents, currency, key_enc, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (user["id"], key_hash(key), key[:7], plan, max_machines, expires_at,
         int(amount_cents or 0), (currency or "USD").upper(),
         _encrypt_key(key), _now()))
    db.commit()
    return {"license_id": cur.lastrowid, "key": key, "plan": plan,
            "max_machines": max_machines, "expires_at": expires_at}, None


@app.post("/api/admin/licenses")
@require_admin
def create_license():
    """Create a license key for a user. M1: manual/admin. M3: Binance Pay webhook."""
    data = request.get_json(force=True, silent=True) or {}
    lic, err = _do_create_license(data.get("email"), data.get("plan", "pro"),
                                  data.get("max_machines", 2), data.get("days", 365),
                                  data.get("amount_cents", 0), data.get("currency", "USD"))
    if err:
        code = 404 if err == "user not found (signup first)" else 400
        return jsonify(error=err), code
    # Full key is returned ONCE here — only its hash is stored.
    return jsonify(lic), 201


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
