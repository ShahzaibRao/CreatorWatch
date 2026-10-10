import sqlite3
import os
from datetime import datetime
from paths import user_data_dir

DB_PATH = os.path.join(user_data_dir(), "data.db")

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
        ("fail_count", "ALTER TABLE profiles ADD COLUMN fail_count INTEGER DEFAULT 0"),
        ("auto_paused_until", "ALTER TABLE profiles ADD COLUMN auto_paused_until TEXT DEFAULT ''"),
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
    conn.execute("UPDATE profiles SET last_check=?, last_error='', fail_count=0 WHERE id=?", (datetime.now().isoformat(), pid))
    conn.commit()
    conn.close()

def set_profile_error(pid, err):
    """Error record karo. 3 lagatar fail par 3 ghante ke liye auto-pause."""
    from datetime import datetime as dt, timedelta
    conn = get_conn()
    # fail_count barhao
    row = conn.execute("SELECT fail_count FROM profiles WHERE id=?", (pid,)).fetchone()
    fails = (row["fail_count"] if row and row["fail_count"] else 0) + 1
    if fails >= 3:
        # Auto-pause for 3 hours
        until = (dt.now() + timedelta(hours=3)).isoformat()
        conn.execute("UPDATE profiles SET last_check=?, last_error=?, fail_count=?, status='paused', auto_paused_until=? WHERE id=?",
                     (dt.now().isoformat(), str(err)[:500], fails, until, pid))
        print(f"[AUTO-PAUSE] profile {pid} 3 fails → 3 ghante pause", flush=True)
    else:
        conn.execute("UPDATE profiles SET last_check=?, last_error=?, fail_count=? WHERE id=?",
                     (dt.now().isoformat(), str(err)[:500], fails, pid))
    conn.commit()
    conn.close()

def resume_expired_auto_pauses():
    """Jin ka 3-ghanta pause khatm ho gaya, unhe wapas active karo."""
    from datetime import datetime as dt
    conn = get_conn()
    now = dt.now().isoformat()
    rows = conn.execute("SELECT id, name FROM profiles WHERE status='paused' AND auto_paused_until != '' AND auto_paused_until < ?",
                        (now,)).fetchall()
    for r in rows:
        conn.execute("UPDATE profiles SET status='active', auto_paused_until='', fail_count=0 WHERE id=?", (r["id"],))
        print(f"[AUTO-RESUME] profile {r['id']} ({r['name']}) wapas active", flush=True)
    conn.commit()
    conn.close()
    return len(rows)

def get_due_profiles():
    """Wo profiles jinka time period guzar gaya ho (last_check + interval).
    Pehle expired auto-pause wale resume karo."""
    resume_expired_auto_pauses()
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
    if status == "active":
        # Manual resume: auto-pause bhi clear karo
        conn.execute("UPDATE profiles SET status=?, auto_paused_until='', fail_count=0 WHERE id=?", (status, pid))
    else:
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

def get_stats():
    """Stats dashboard ke liye data."""
    from datetime import datetime as dt, timedelta
    conn = get_conn()
    # 1. Roz kitni videos (pichle 30 din)
    daily = conn.execute("""
        SELECT substr(downloaded_at, 1, 10) as day, COUNT(*) as n
        FROM videos WHERE status='done'
        AND downloaded_at >= ?
        GROUP BY day ORDER BY day
    """, ((dt.now() - timedelta(days=30)).isoformat(),)).fetchall()
    # 2. Platform-wise
    by_platform = conn.execute("""
        SELECT p.platform, COUNT(*) as n FROM videos v
        JOIN profiles p ON p.id = v.profile_id
        WHERE v.status='done' GROUP BY p.platform ORDER BY n DESC
    """).fetchall()
    # 3. Top 10 prospects
    top_prospects = conn.execute("""
        SELECT p.name, p.platform, COUNT(*) as n FROM videos v
        JOIN profiles p ON p.id = v.profile_id
        WHERE v.status='done' GROUP BY p.id ORDER BY n DESC LIMIT 10
    """).fetchall()
    # 4. Hour-wise (kis waqt zyada videos aati hain)
    by_hour = conn.execute("""
        SELECT CAST(substr(downloaded_at, 12, 2) AS INTEGER) as hour, COUNT(*) as n
        FROM videos WHERE status='done' GROUP BY hour ORDER BY hour
    """).fetchall()
    # 5. Total storage
    total_size = conn.execute(
        "SELECT COALESCE(SUM(filesize),0) as s FROM videos WHERE status='done'").fetchone()["s"]
    conn.close()
    return {
        "daily": [{"day": r["day"], "n": r["n"]} for r in daily],
        "by_platform": [{"platform": r["platform"], "n": r["n"]} for r in by_platform],
        "top_prospects": [{"name": r["name"], "platform": r["platform"], "n": r["n"]} for r in top_prospects],
        "by_hour": [{"hour": r["hour"], "n": r["n"]} for r in by_hour],
        "total_size": total_size,
    }

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

# ============ BACKUP ============
def backup_dir():
    """Backup folder: Documents/CreatorWatch-Backups"""
    import os
    d = os.path.join(os.path.expanduser("~"), "Documents", "CreatorWatch-Backups")
    os.makedirs(d, exist_ok=True)
    return d

def create_backup():
    """data.db + cookies.txt ka backup banao. Returns (filepath, msg)."""
    import os, shutil
    from datetime import datetime as dt
    from paths import user_data_dir
    try:
        src_db = DB_PATH
        src_ck = os.path.join(user_data_dir(), "cookies.txt")
        if not os.path.exists(src_db):
            return None, "data.db nahi mili!"
        ts = dt.now().strftime("%Y-%m-%d_%H-%M")
        name = f"backup_{ts}.zip"
        fp = os.path.join(backup_dir(), name)
        import zipfile
        with zipfile.ZipFile(fp, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(src_db, "data.db")
            if os.path.exists(src_ck):
                z.write(src_ck, "cookies.txt")
        # Purane backups: sirf aakhri 10 rakho
        bks = sorted([f for f in os.listdir(backup_dir()) if f.startswith("backup_") and f.endswith(".zip")])
        for old in bks[:-10]:
            try: os.remove(os.path.join(backup_dir(), old))
            except Exception: pass
        # Last backup time save karo (auto-backup ke liye)
        set_setting("last_backup", dt.now().isoformat())
        sz = os.path.getsize(fp)
        return fp, f"Backup ho gaya: {name} ({sz//1024} KB)"
    except Exception as e:
        return None, f"Backup fail: {e}"

def list_backups():
    """Maujood backups ki list."""
    import os
    from datetime import datetime as dt
    out = []
    d = backup_dir()
    if not os.path.exists(d):
        return out
    for f in sorted(os.listdir(d), reverse=True):
        if f.startswith("backup_") and f.endswith(".zip"):
            fp = os.path.join(d, f)
            out.append({
                "name": f,
                "size_kb": os.path.getsize(fp) // 1024,
                "date": dt.fromtimestamp(os.path.getmtime(fp)).strftime("%d %b, %H:%M"),
            })
    return out

def restore_backup(name):
    """Backup se data.db + cookies.txt wapis lao. Returns msg."""
    import os, zipfile, shutil
    from paths import user_data_dir
    fp = os.path.join(backup_dir(), name)
    if not os.path.exists(fp):
        return "Backup file nahi mili!"
    try:
        # Pehle current ka backup le lo (safety)
        create_backup()
        with zipfile.ZipFile(fp, "r") as z:
            # data.db restore
            if "data.db" in z.namelist():
                with z.open("data.db") as src, open(DB_PATH, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            # cookies.txt restore
            if "cookies.txt" in z.namelist():
                ck = os.path.join(user_data_dir(), "cookies.txt")
                with z.open("cookies.txt") as src, open(ck, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        return f"Restore ho gaya: {name} — app restart karo!"
    except Exception as e:
        return f"Restore fail: {e}"

def auto_backup_check():
    """Hafte me ek bar khud backup (app start par check)."""
    from datetime import datetime as dt, timedelta
    last = get_setting("last_backup", "")
    try:
        last_dt = dt.fromisoformat(last) if last else None
    except Exception:
        last_dt = None
    if not last_dt or (dt.now() - last_dt) > timedelta(days=7):
        fp, msg = create_backup()
        print(f"[AUTO-BACKUP] {msg}", flush=True)
        return msg
    return None

def get_posting_pattern(pid):
    """Ek prospect ka posting pattern: hour-wise, day-wise + interval suggestion."""
    from datetime import datetime as dt
    conn = get_conn()
    prof = conn.execute("SELECT * FROM profiles WHERE id=?", (pid,)).fetchone()
    if not prof:
        conn.close()
        return None
    prof = dict(prof)
    # Hour-wise (0-23)
    by_hour = conn.execute("""
        SELECT CAST(substr(downloaded_at, 12, 2) AS INTEGER) as h, COUNT(*) as n
        FROM videos WHERE profile_id=? AND status='done' GROUP BY h ORDER BY h
    """, (pid,)).fetchall()
    # Day-wise (0=Mon ... 6=Sun) — SQLite strftime %w: 0=Sun
    by_day = conn.execute("""
        SELECT CAST(strftime('%w', downloaded_at) AS INTEGER) as d, COUNT(*) as n
        FROM videos WHERE profile_id=? AND status='done' GROUP BY d
    """, (pid,)).fetchall()
    # Total videos + pehli/aakhri date
    info = conn.execute("""
        SELECT COUNT(*) as total, MIN(downloaded_at) as first, MAX(downloaded_at) as last
        FROM videos WHERE profile_id=? AND status='done'
    """, (pid,)).fetchone()
    conn.close()

    hours = [0]*24
    for r in by_hour:
        if r["h"] is not None and 0 <= r["h"] < 24:
            hours[r["h"]] = r["n"]
    # SQLite: 0=Sun,1=Mon... → 0=Mon order me convert
    days = [0]*7
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for r in by_day:
        d = r["d"]
        idx = (d - 1) % 7  # Sun(0)→6, Mon(1)→0
        days[idx] = r["n"]

    total = info["total"] or 0
    # Interval suggestion
    suggestion, reason = "", ""
    if total >= 5 and info["first"] and info["last"]:
        try:
            f = dt.fromisoformat(info["first"])
            l = dt.fromisoformat(info["last"])
            days_span = max((l - f).days, 1)
            per_day = total / days_span
            if per_day >= 3:
                suggestion, reason = "15 min", f"Roz ~{per_day:.0f} videos — frequent poster!"
            elif per_day >= 1:
                suggestion, reason = "60 min", f"Roz ~{per_day:.1f} videos — daily poster"
            elif per_day >= 0.3:
                suggestion, reason = "180 min (3 ghante)", f"Hafte me ~{per_day*7:.0f} videos"
            else:
                suggestion, reason = "720 min (12 ghante)", f"Mahine me ~{per_day*30:.0f} videos — kam post karta hai"
        except Exception:
            pass
    # Peak hour
    peak_hour = max(range(24), key=lambda h: hours[h]) if total else None

    return {
        "profile": prof,
        "hours": hours,
        "days": days,
        "day_names": day_names,
        "total": total,
        "suggestion": suggestion,
        "reason": reason,
        "peak_hour": peak_hour,
        "first": (info["first"] or "")[:10],
        "last": (info["last"] or "")[:10],
    }

def set_interval(pid, minutes):
    conn = get_conn()
    conn.execute("UPDATE profiles SET interval_minutes=? WHERE id=?", (int(minutes), pid))
    conn.commit()
    conn.close()

def mark_video_seen(vid):
    """Ek video ko seen mark karo (NEW tag hat jayega)."""
    conn = get_conn()
    conn.execute("UPDATE videos SET seen=1 WHERE id=?", (vid,))
    conn.commit()
    conn.close()

def mark_profile_seen(pid):
    """Prospect ki saari videos seen mark karo."""
    conn = get_conn()
    conn.execute("UPDATE videos SET seen=1 WHERE profile_id=? AND seen=0", (pid,))
    conn.commit()
    conn.close()
