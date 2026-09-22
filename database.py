import sqlite3
import os
from datetime import datetime
from paths import app_dir

DB_PATH = os.path.join(app_dir(), "data.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        platform TEXT NOT NULL,
        url TEXT NOT NULL UNIQUE,
        folder TEXT NOT NULL,
        created_at TEXT,
        last_check TEXT,
        status TEXT DEFAULT 'active',
        interval_minutes INTEGER DEFAULT 15,
        last_error TEXT DEFAULT '',
        quality TEXT DEFAULT '720p',
        scope TEXT DEFAULT 'both',
        method TEXT DEFAULT 'auto'
    )
    """)
    # migration for old DBs
    for col, ddl in [
        ("interval_minutes", "ALTER TABLE profiles ADD COLUMN interval_minutes INTEGER DEFAULT 15"),
        ("last_error", "ALTER TABLE profiles ADD COLUMN last_error TEXT DEFAULT ''"),
        ("quality", "ALTER TABLE profiles ADD COLUMN quality TEXT DEFAULT '720p'"),
        ("scope", "ALTER TABLE profiles ADD COLUMN scope TEXT DEFAULT 'both'"),
        ("method", "ALTER TABLE profiles ADD COLUMN method TEXT DEFAULT 'auto'"),
        ("seen", "ALTER TABLE videos ADD COLUMN seen INTEGER DEFAULT 1"),
    ]:
        try:
            cur.execute(ddl)
        except Exception:
            pass  # column already exists
    cur.execute("""
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER,
        video_id TEXT,
        title TEXT,
        filename TEXT,
        filesize INTEGER DEFAULT 0,
        downloaded_at TEXT,
        status TEXT DEFAULT 'done',
        seen INTEGER DEFAULT 1,
        UNIQUE(profile_id, video_id),
        FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    conn.commit()
    conn.close()

def get_max_workers():
    try:
        return max(1, min(int(get_setting("max_workers", 3) or 3), 10))
    except (TypeError, ValueError):
        return 3

def get_downloads_root():
    """Global save location (user setting) ya default ~/Downloads/CreatorWatch."""
    import os as _os
    root = get_setting("downloads_root", "") or ""
    root = root.strip()
    if not root:
        root = _os.path.join(_os.path.expanduser("~"), "Downloads", "CreatorWatch")
    return root

def set_downloads_root(path):
    set_setting("downloads_root", path)

def disk_free_gb(path):
    import shutil
    try:
        u = shutil.disk_usage(path if os.path.exists(path) else os.path.dirname(path) or ".")
        return round(u.free / (1024 ** 3), 1), round(u.total / (1024 ** 3), 1)
    except Exception:
        return None, None

def add_profile(name, platform, url, folder, interval_minutes=15, quality="720p", scope="both", method="auto"):
    conn = get_conn()
    cur = conn.cursor()
    if scope not in ("both", "videos", "shorts"):
        scope = "both"
    if method not in ("auto", "direct", "po"):
        method = "auto"
    try:
        cur.execute(
            "INSERT INTO profiles (name, platform, url, folder, created_at, interval_minutes, quality, scope, method) VALUES (?,?,?,?,?,?,?,?,?)",
            (name, platform, url, folder, datetime.now().isoformat(), int(interval_minutes or 15), quality or "720p", scope, method)
        )
        conn.commit()
        pid = cur.lastrowid
    except sqlite3.IntegrityError:
        pid = None
    conn.close()
    return pid

def update_profile(pid, name, url, interval_minutes, quality, folder=None, scope=None, method=None):
    """Edit: name/url/interval/quality (+optional folder/scope/method) update."""
    conn = get_conn()
    sets = ["name=?", "url=?", "interval_minutes=?", "quality=?", "platform=?"]
    vals = [name, url, int(interval_minutes or 15), quality or "720p", _platform(url)]
    if folder:
        sets.append("folder=?")
        vals.append(folder)
    if scope in ("both", "videos", "shorts"):
        sets.append("scope=?")
        vals.append(scope)
    if method in ("auto", "direct", "po"):
        sets.append("method=?")
        vals.append(method)
    vals.append(pid)
    conn.execute(f"UPDATE profiles SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit()
    conn.close()

def _platform(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "tiktok.com" in u:
        return "tiktok"
    if "instagram.com" in u:
        return "instagram"
    if "twitter.com" in u or "x.com" in u:
        return "twitter"
    return "unknown"

def get_profiles():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM profiles ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_profile(pid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM profiles WHERE id=?", (pid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_last_check(pid):
    conn = get_conn()
    conn.execute("UPDATE profiles SET last_check=?, last_error='' WHERE id=?", (datetime.now().isoformat(), pid))
    conn.commit()
    conn.close()

def set_profile_error(pid, err):
    conn = get_conn()
    conn.execute("UPDATE profiles SET last_check=?, last_error=? WHERE id=?",
                 (datetime.now().isoformat(), str(err)[:500], pid))
    conn.commit()
    conn.close()

def get_due_profiles():
    """Wo profiles jinka time period guzar gaya ho (last_check + interval)."""
    from datetime import datetime as dt
    due = []
    for p in get_profiles():
        if p.get("status") != "active":
            continue
        interval = int(p.get("interval_minutes") or 15)
        lc = p.get("last_check")
        if not lc:
            due.append(p)  # kabhi check nahi hua -> due
            continue
        try:
            last = dt.fromisoformat(lc)
            elapsed = (dt.now() - last).total_seconds() / 60
            if elapsed >= interval:
                due.append(p)
        except Exception:
            due.append(p)
    return due

def delete_profile(pid):
    conn = get_conn()
    conn.execute("DELETE FROM videos WHERE profile_id=?", (pid,))
    conn.execute("DELETE FROM profiles WHERE id=?", (pid,))
    conn.commit()
    conn.close()

def add_video(profile_id, video_id, title, filename, filesize=0):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO videos (profile_id, video_id, title, filename, filesize, downloaded_at, seen) VALUES (?,?,?,?,?,?,?)",
            (profile_id, video_id, title, filename, filesize, datetime.now().isoformat(), 0)
        )
        conn.commit()
        ok = True
    except sqlite3.IntegrityError:
        ok = False  # already downloaded
    conn.close()
    return ok

def get_unseen(limit=20):
    """Nayi downloads jo user ne abhi dekhi nahi (notification bell ke liye)."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT v.*, p.name as profile_name, p.platform FROM videos v
        JOIN profiles p ON p.id = v.profile_id
        WHERE v.status='done' AND v.seen=0
        ORDER BY v.downloaded_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def mark_all_seen():
    conn = get_conn()
    conn.execute("UPDATE videos SET seen=1 WHERE seen=0")
    conn.commit()
    conn.close()

def unseen_profiles():
    """Kaun se profile IDs me unseen videos hain (NEW pill ke liye)."""
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT profile_id FROM videos WHERE status='done' AND seen=0").fetchall()
    conn.close()
    return {r["profile_id"] for r in rows}

def youtube_blocked():
    """Kaun se YouTube profiles wall-error me hain (IP suggestion banner ke liye)."""
    conn = get_conn()
    rows = conn.execute("SELECT id, name, last_error FROM profiles WHERE platform='youtube' AND status='active'").fetchall()
    conn.close()
    out = []
    for r in rows:
        err = r["last_error"] or ""
        if any(h in err for h in ("not a bot", "needs to be reloaded", "PO-token")):
            out.append(dict(r))
    return out

def video_exists(profile_id, video_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM videos WHERE profile_id=? AND video_id=?", (profile_id, video_id)
    ).fetchone()
    conn.close()
    return row is not None  # done ho ya skipped — dobara kabhi download nahi hogi

def mark_seen(profile_id, video_id, title=""):
    """Purani video ko bina download kiye 'dekha hua' mark karo — phir kabhi download nahi hogi."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO videos (profile_id, video_id, title, filename, filesize, downloaded_at, status) VALUES (?,?,?,?,?,?,?)",
            (profile_id, video_id, title, "", 0, datetime.now().isoformat(), "skipped")
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def set_status(pid, status):
    conn = get_conn()
    conn.execute("UPDATE profiles SET status=? WHERE id=?", (status, pid))
    conn.commit()
    conn.close()

def get_recent_videos(limit=20):
    conn = get_conn()
    rows = conn.execute("""
        SELECT v.*, p.name as profile_name, p.platform FROM videos v
        JOIN profiles p ON p.id = v.profile_id
        WHERE v.status='done'
        ORDER BY v.downloaded_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_metrics(downloads_root="downloads"):
    conn = get_conn()
    total_profiles = conn.execute("SELECT COUNT(*) c FROM profiles").fetchone()["c"]
    total_videos = conn.execute("SELECT COUNT(*) c FROM videos WHERE status='done'").fetchone()["c"]
    per_profile = conn.execute("""
        SELECT p.id, p.name, p.platform, COUNT(CASE WHEN v.status='done' THEN 1 END) as video_count
        FROM profiles p LEFT JOIN videos v ON v.profile_id = p.id
        GROUP BY p.id
    """).fetchall()
    folders = {r["folder"] for r in conn.execute("SELECT folder FROM profiles")}
    conn.close()

    # storage: sab profile folders (custom locations samet) + global root
    import os as _os
    try:
        folders.add(get_downloads_root())
    except Exception:
        pass
    total_bytes = 0
    for f in folders:
        if not f or not _os.path.isdir(f):
            continue
        for root, _, files in _os.walk(f):
            for fn in files:
                try:
                    total_bytes += _os.path.getsize(_os.path.join(root, fn))
                except OSError:
                    pass

    return {
        "total_profiles": total_profiles,
        "total_videos": total_videos,
        "storage_bytes": total_bytes,
        "storage_mb": round(total_bytes / (1024*1024), 2),
        "per_profile": [dict(r) for r in per_profile],
    }
