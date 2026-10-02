"""License server DB layer.

Postgres jab DATABASE_URL set ho (production/k3s — tumhare platform ka
standard pattern), warna SQLite (local dev zero-config: `python app.py`).

Dono backends ek jesa interface:
  db = get_db()                       # per-request connection (Flask g)
  cur = db.execute("SELECT ... WHERE email = ?", (email,))
  cur.fetchone() / cur.fetchall()     # plain dicts
  db.commit() / db.close()
  db.dialect                          # "postgres" ya "sqlite"

Compatibility notes:
  - `?` placeholders dono par chalte hain (postgres ke liye %s me translate).
  - INSERT ke baad id: `... RETURNING id` + fetchone()["id"]
    (SQLite 3.35+ aur Postgres dono support karte hain).
"""

import os

from flask import g

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DIALECT = "postgres" if DATABASE_URL else "sqlite"
DB_PATH = os.environ.get("LICENSE_DB",
                         os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "licenses.db"))

if DIALECT == "postgres":
    import psycopg2
    import psycopg2.extras
    IntegrityError = psycopg2.IntegrityError
    _PK = "SERIAL PRIMARY KEY"
else:
    import sqlite3
    IntegrityError = sqlite3.IntegrityError
    _PK = "INTEGER PRIMARY KEY AUTOINCREMENT"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS users (
  id {_PK},
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS licenses (
  id {_PK},
  user_id INTEGER NOT NULL REFERENCES users(id),
  key_hash TEXT UNIQUE NOT NULL,
  key_prefix TEXT NOT NULL,
  plan TEXT NOT NULL DEFAULT 'pro',
  max_machines INTEGER NOT NULL DEFAULT 2,
  expires_at TEXT,
  revoked INTEGER NOT NULL DEFAULT 0,
  amount_cents INTEGER NOT NULL DEFAULT 0,
  currency TEXT NOT NULL DEFAULT 'USD',
  key_enc TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activations (
  id {_PK},
  license_id INTEGER NOT NULL REFERENCES licenses(id),
  machine_id TEXT NOT NULL,
  activated_at TEXT NOT NULL,
  UNIQUE(license_id, machine_id)
);
"""


class _Cursor:
    def __init__(self, raw):
        self._raw = raw

    def fetchone(self):
        r = self._raw.fetchone()
        return dict(r) if r is not None else None

    def fetchall(self):
        return [dict(r) for r in self._raw.fetchall()]


class _Conn:
    """Thin wrapper: ? placeholders + dict rows, dono dialects par."""

    def __init__(self, raw, dialect):
        self._raw = raw
        self.dialect = dialect

    def execute(self, sql, params=()):
        if self.dialect == "postgres":
            sql = sql.replace("?", "%s")
            cur = self._raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = self._raw.cursor()
        cur.execute(sql, params)
        return _Cursor(cur)

    def commit(self):
        self._raw.commit()

    def close(self):
        try:
            self._raw.close()
        except Exception:
            pass


def secret_dir():
    """Key-secret file kahan rakhen: sqlite DB ke sath, warna app folder."""
    if DIALECT == "postgres":
        return os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.abspath(DB_PATH))


def _connect():
    if DIALECT == "postgres":
        return _Conn(psycopg2.connect(DATABASE_URL), "postgres")
    raw = sqlite3.connect(DB_PATH)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    return _Conn(raw, "sqlite")


def _migrate_schema(conn):
    """Purani DBs me naye columns (amount_cents, currency, key_enc)."""
    if conn.dialect == "postgres":
        cols = {r["column_name"] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = 'licenses'").fetchall()}
    else:
        cols = {r[1] for r in conn._raw.execute(
            "PRAGMA table_info(licenses)").fetchall()}
    for col, ddl in (("amount_cents", "ADD COLUMN amount_cents INTEGER NOT NULL DEFAULT 0"),
                     ("currency", "ADD COLUMN currency TEXT NOT NULL DEFAULT 'USD'"),
                     ("key_enc", "ADD COLUMN key_enc TEXT")):
        if col not in cols:
            try:
                conn.execute(f"ALTER TABLE licenses {ddl}")
            except Exception:
                pass  # concurrent first request ne pehle add kar diya
    conn.commit()


_schema_ready = False


def _ensure_schema(conn):
    global _schema_ready
    if _schema_ready:
        return
    if conn.dialect == "postgres":
        # psycopg2 ek execute me multi-statement chala leta hai
        conn._raw.cursor().execute(SCHEMA)
    else:
        conn._raw.executescript(SCHEMA)
    _migrate_schema(conn)
    _schema_ready = True


def get_db():
    if "db" not in g:
        g.db = _connect()
    _ensure_schema(g.db)  # gunicorn me __main__ nahi chalta — pehli request par pakka
    return g.db


def close_db():
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    global _schema_ready
    _schema_ready = False
    conn = _connect()
    try:
        _ensure_schema(conn)
    finally:
        conn.close()
