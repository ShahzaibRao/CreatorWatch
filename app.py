import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, redirect, url_for, jsonify, g
from apscheduler.schedulers.background import BackgroundScheduler
import yt_dlp
import database as db
from paths import app_dir, is_frozen
from translations import LANGS, text as _text
from downloader import detect_platform, prospect_folder, check_profile, check_all_profiles, check_due_profiles, first_run

VERSION = "0.1.0"
REPO = "ShahzaibRao/CreatorWatch"

app = Flask(__name__)
db.init_db()

def _lang():
    c = request.cookies.get("lang", "ur") if request else "ur"
    return c if c in LANGS else "ur"

def T(key):
    try:
        return _text(_lang(), key)
    except Exception:
        return _text("en", key)

@app.before_request
def _set_lang():
    g.lang = _lang()

@app.context_processor
def _inject_lang():
    return {"t": lambda k: _text(g.get("lang", "ur"), k), "lang": g.get("lang", "ur"), "langs": LANGS}

@app.route("/lang/<code>")
def set_lang(code):
    if code not in LANGS:
        code = "ur"
    resp = redirect(request.referrer or url_for("dashboard"))
    resp.set_cookie("lang", code, max_age=31536000)
    return resp

# ---- Multi-threading (limited): N profiles ek sath (dashboard se set, 1-10),
# har profile ke andar videos sequence me (site rate-limit + CPU/RAM safe).
executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="dl")
RUNNING = set()  # pids with active job
RUNNING_LOCK = threading.Lock()

def max_workers():
    return db.get_max_workers()

COOKIES_PATH = os.path.join(app_dir(), "cookies.txt")

TEST_URLS = {
    "instagram": "https://www.instagram.com/instagram/",
    "twitter": "https://twitter.com/twitter",
    "tiktok": "https://www.tiktok.com/@tiktok",
    "youtube": "https://www.youtube.com/@YouTube",
}

def cookies_info():
    """cookies.txt ka format + expiry check. No login test, sirf file health."""
    if not os.path.exists(COOKIES_PATH):
        return {"exists": False, "sites": {
            k: {"label": v[0], "state": "missing" if v[3] else "optional",
                "detail": "cookies import nahi huin" if v[3] else "zaroorat nahi"}
            for k, v in SITE_RULES.items()}}
    try:
        st = os.stat(COOKIES_PATH)
        lines = open(COOKIES_PATH, encoding="utf-8", errors="ignore").read().splitlines()
    except Exception as e:
        return {"exists": True, "error": str(e)}
    header_ok = any("Netscape HTTP Cookie File" in l for l in lines[:5])
    domains, usable, expired = set(), 0, 0
    now = time.time()
    for l in lines:
        if not l or l.startswith("#"):
            continue
        parts = l.split("\t")
        if len(parts) < 7:
            continue
        try:
            exp = int(parts[4])
        except ValueError:
            continue
        if exp and exp < now:
            expired += 1
            continue
        usable += 1
        domains.add(parts[0].lstrip("."))
    return {
        "exists": True, "header_ok": header_ok, "usable": usable,
        "expired": expired, "domains": sorted(domains)[:15],
        "size_kb": round(st.st_size / 1024, 1),
        "updated": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
        "sites": _site_cookie_status(lines),
    }

SITE_RULES = {
    # site: (label, match domains, required cookie names, required?)
    "instagram": ("Instagram", ("instagram.com",), ("sessionid",), True),
    "twitter": ("X (Twitter)", ("x.com", "twitter.com"), ("auth_token",), True),
    "youtube": ("YouTube", ("youtube.com",), (), False),
    "tiktok": ("TikTok", ("tiktok.com",), (), False),
}

def _site_cookie_status(lines):
    now = time.time()
    by_dom = {}
    for l in lines:
        if not l or l.startswith("#"):
            continue
        parts = l.split("\t")
        if len(parts) < 7:
            continue
        try:
            exp = int(parts[4])
        except ValueError:
            continue
        by_dom.setdefault(parts[0].lstrip("."), {})[parts[5]] = (exp and exp < now)
    out = {}
    for key, (label, doms, required, must) in SITE_RULES.items():
        merged = {}
        for d, ck in by_dom.items():
            if any(d == x or d.endswith("." + x) for x in doms):
                merged.update(ck)
        if not merged:
            out[key] = {"label": label, "state": "missing" if must else "optional",
                        "detail": "koi cookie nahi" + (" — login karke import karo" if must else " (baghair cookies chalta hai)")}
            continue
        if not required:
            out[key] = {"label": label, "state": "present",
                        "detail": f"{len(merged)} cookies (optional — baghair bhi chalta hai)"}
            continue
        missing = [r for r in required if r not in merged]
        expired = [r for r in required if r in merged and merged[r]]
        if missing:
            out[key] = {"label": label, "state": "login",
                        "detail": f"login missing ({', '.join(missing)} nahi) — logout ho? login karke dobara import karo"}
        elif expired:
            out[key] = {"label": label, "state": "expired",
                        "detail": "session expire — dobara login karke import karo"}
        else:
            out[key] = {"label": label, "state": "ready", "detail": "login cookies OK"}
    return out

def live_cookie_test(platform, url):
    """Asli fetch cookies ke sath — batata hai login chal raha ya nahi."""
    if not os.path.exists(COOKIES_PATH):
        return False, "cookies.txt mojood nahi — pehle import karo"
    if platform == "instagram":
        try:
            from downloader import ig_fetch
            entries = ig_fetch(url, 1)
            return True, f"OK — latest post mili ({entries[0]['id']}), login kaam kar raha hai"
        except Exception as e:
            return False, str(e)[:250]
    if platform == "twitter":
        try:
            from downloader import tw_fetch
            entries = tw_fetch(url, 1)
            return True, f"OK — latest tweet mili ({entries[0]['id']}), login kaam kar raha hai"
        except Exception as e:
            return False, str(e)[:250]
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True,
            "playlistend": 3, "skip_download": True, "cookiefile": COOKIES_PATH}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            return False, "kuch nahi mila — cookies expire ho sakti hain"
        if info.get("_type") != "playlist" and "id" in info:
            return True, "OK — login kaam kar raha hai"
        n = len([e for e in (info.get("entries") or []) if e])
        if n > 0:
            return True, f"OK — {n} items mile, login kaam kar raha hai"
        return False, "login required — cookies expire/ghalat hain, dobara import karo"
    except Exception as e:
        return False, str(e)[:250]

def run_first_download(pid):
    """First time add par SIRF latest 1 video download, purani skip (pool worker)."""
    start_job(pid, "first")
    try:
        p = db.get_profile(pid)
        if not p:
            finish_job(pid, "profile nahi mila")
            return
        print(f"[FIRST] {p['name']} {p['url']}", flush=True)
        new, errs = first_run(p, progress=job_cb(pid))
        print(f"[FIRST DONE] {p['name']} new={new} errors={errs[:2] if errs else []}", flush=True)
        finish_job(pid, f"{new} new" if new else (errs[0][:120] if errs else "koi fresh upload nahi"))
    except Exception as e:
        print(f"[FIRST FAIL] {e}", flush=True)
        finish_job(pid, f"fail: {e}")
    finally:
        with RUNNING_LOCK:
            RUNNING.discard(pid)

def run_check(pid):
    """Manual/auto check pool worker me (progress bar ke sath)."""
    start_job(pid, "check")
    try:
        p = db.get_profile(pid)
        if not p:
            finish_job(pid, "profile nahi mila")
            return
        new, errs = check_profile(p, progress=job_cb(pid))
        finish_job(pid, f"{new} new" if new else (errs[0][:120] if errs else "koi fresh upload nahi"))
    except Exception as e:
        finish_job(pid, f"fail: {e}")
    finally:
        with RUNNING_LOCK:
            RUNNING.discard(pid)

def submit(pid, first=False):
    """Pool me submit (busy ya limit-full ho to skip). Returns True agar submit hua."""
    with RUNNING_LOCK:
        if pid in RUNNING:
            return False
        if len(RUNNING) >= max_workers():
            return False
        RUNNING.add(pid)
    executor.submit(run_first_download if first else run_check, pid)
    return True

def submit_due():
    """Scheduler: due profiles pool me (max limit, busy skip)."""
    try:
        for p in db.get_due_profiles():
            submit(p["id"])
    except Exception as e:
        print(f"[SCHED FAIL] {e}", flush=True)

JOBS = {}
JOBS_LOCK = threading.Lock()

def start_job(pid, kind):
    with JOBS_LOCK:
        JOBS[pid] = {"state": "active", "kind": kind, "stage": "start",
                     "done": 0, "total": 1, "pct": None, "title": "...",
                     "result": "", "ts": time.time()}

def job_cb(pid):
    def _cb(u):
        with JOBS_LOCK:
            if pid in JOBS:
                JOBS[pid].update({k: u.get(k, JOBS[pid].get(k)) for k in ("stage", "done", "total", "pct", "title")})
                JOBS[pid]["ts"] = time.time()
    return _cb

def finish_job(pid, result):
    with JOBS_LOCK:
        if pid in JOBS:
            JOBS[pid].update({"state": "done", "result": result, "pct": 100,
                              "done": JOBS[pid].get("total", 1), "ts": time.time()})

@app.route("/")
def dashboard():
    profiles = db.get_profiles()
    metrics = db.get_metrics()
    recent = db.get_recent_videos(20)
    unseen = db.get_unseen(20)
    unseen_pids = db.unseen_profiles()
    cookies_ok = os.path.exists(os.path.join(os.path.dirname(__file__), "cookies.txt"))
    return render_template("dashboard.html", profiles=profiles, metrics=metrics,
                           recent=recent, cookies_ok=cookies_ok, version=VERSION,
                           unseen=unseen, unseen_pids=unseen_pids)

@app.route("/add", methods=["POST"])
def add():
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    quality = request.form.get("quality", "720p").strip()
    if quality not in ("best", "1080p", "720p", "480p", "360p"):
        quality = "720p"
    try:
        interval = int(request.form.get("interval", "15"))
    except ValueError:
        interval = 15
    interval = max(5, min(interval, 1440))  # 5 min se 24h tak
    if not name or not url:
        return redirect(url_for("dashboard"))
    platform = detect_platform(url)
    folder = prospect_folder(name, platform)
    pid = db.add_profile(name, platform, url, folder, interval, quality)
    if pid:
        # first-time latest download pool worker me (user ko wait nahi karna)
        submit(pid, first=True)
    return redirect(url_for("dashboard"))

@app.route("/edit/<int:pid>", methods=["GET", "POST"])
def edit(pid):
    p = db.get_profile(pid)
    if not p:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip() or p["name"]
        url = request.form.get("url", "").strip() or p["url"]
        quality = request.form.get("quality", "720p").strip()
        if quality not in ("best", "1080p", "720p", "480p", "360p"):
            quality = "720p"
        try:
            interval = int(request.form.get("interval", "15"))
        except ValueError:
            interval = 15
        interval = max(5, min(interval, 1440))
        db.update_profile(pid, name, url, interval, quality)
        return redirect(url_for("dashboard"))
    return render_template("edit.html", p=p)

@app.route("/delete/<int:pid>")
def delete(pid):
    db.delete_profile(pid)
    return redirect(url_for("dashboard"))

@app.route("/pause/<int:pid>")
def pause(pid):
    db.set_status(pid, "paused")
    return redirect(url_for("dashboard"))

@app.route("/resume/<int:pid>")
def resume(pid):
    db.set_status(pid, "active")
    return redirect(url_for("dashboard"))

@app.route("/check/<int:pid>")
def check_one(pid):
    p = db.get_profile(pid)
    if not p:
        return redirect(url_for("dashboard"))
    submit(pid)
    return redirect(url_for("dashboard"))

@app.route("/check_all")
def check_all():
    for p in db.get_profiles():
        if p.get("status") != "active":
            continue
        submit(p["id"])
    return redirect(url_for("dashboard"))

@app.route("/api/jobs")
def api_jobs():
    with JOBS_LOCK:
        jobs = {str(k): v for k, v in JOBS.items()
                if v.get("state") == "active" or time.time() - v.get("ts", 0) < 120}
    with RUNNING_LOCK:
        busy = len(RUNNING)
    return jsonify({"jobs": jobs, "workers": {"busy": busy, "max": max_workers()}})

@app.route("/settings", methods=["GET", "POST"])
def settings():
    import os as _os
    msg = ""
    if request.method == "POST":
        try:
            n = int(request.form.get("max_workers", "3"))
        except ValueError:
            n = 3
        n = max(1, min(n, 10))
        db.set_setting("max_workers", n)
        msg = f"Save ho gaya: {n} parallel workers"
    return render_template("settings.html", n=max_workers(), msg=msg,
                           suggestion=None, cores=_os.cpu_count() or 4)

def suggest_workers(cores, ram_gb, speed_mbps):
    """Bottleneck = sab se choti value. 1 core system ke liye chhoro."""
    by_cpu = max(1, min((cores or 4) - 1, 8))
    by_ram = max(1, int((ram_gb or 4) * 1024 * 0.4 // 450))
    by_net = max(1, int((speed_mbps or 20) // 10))
    best = max(1, min(by_cpu, by_ram, by_net, 10))
    bottle = {"by_cpu": by_cpu, "by_ram": by_ram, "by_net": by_net}
    neck = min(bottle, key=bottle.get)
    why = {"by_cpu": "CPU (ffmpeg merge 1 core khata hai)", "by_ram": "RAM (har worker ~450MB peak)",
           "by_net": "Net speed (har worker ~10 Mbps)"}[neck]
    return {"n": best, "by_cpu": by_cpu, "by_ram": by_ram, "by_net": by_net, "why": why}

@app.route("/settings/calc", methods=["POST"])
def settings_calc():
    import os as _os
    try:
        cores = max(1, min(int(request.form.get("cores", "4")), 64))
    except ValueError:
        cores = 4
    try:
        ram = max(1, min(float(request.form.get("ram", "8")), 512))
    except ValueError:
        ram = 8
    try:
        speed = max(1, min(float(request.form.get("speed", "50")), 10000))
    except ValueError:
        speed = 50
    s = suggest_workers(cores, ram, speed)
    s.update({"cores": cores, "ram": ram, "speed": speed})
    return render_template("settings.html", n=max_workers(), msg="", suggestion=s, cores=cores)

@app.route("/settings/apply", methods=["POST"])
def settings_apply():
    try:
        n = max(1, min(int(request.form.get("n", "3")), 10))
    except ValueError:
        n = 3
    db.set_setting("max_workers", n)
    return render_template("settings.html", n=n, msg=f"Apply ho gaya: {n} parallel workers",
                           suggestion=None, cores=__import__("os").cpu_count() or 4)

@app.route("/api/notifications")
def api_notifications():
    items = db.get_unseen(20)
    return jsonify({"count": len(db.get_unseen(100)), "items": items})

@app.route("/notifications/read")
def notifications_read():
    db.mark_all_seen()
    return redirect(url_for("dashboard"))

@app.route("/cookies", methods=["GET", "POST"])
def cookies_page():
    msg, msg_ok = request.args.get("msg", ""), request.args.get("ok", "") == "1"
    if request.method == "POST":
        content = request.form.get("cookies", "").strip().replace("\r\n", "\n")
        if not content:
            return redirect(url_for("cookies_page", msg="Khali hai — cookies paste karo", ok="0"))
        if "Netscape HTTP Cookie File" not in content.split("\n", 5)[0] and "# Netscape" not in content[:200] and "Netscape" not in content[:500]:
            return redirect(url_for("cookies_page", msg="Ghalat format! 'Get cookies.txt LOCALLY' extension se Netscape format me export karo", ok="0"))
        try:
            open(COOKIES_PATH, "w", encoding="utf-8").write(content + "\n")
            info = cookies_info()
            return redirect(url_for("cookies_page", msg=f"Save ho gayin: {info.get('usable',0)} cookies, {len(info.get('domains',[]))} sites", ok="1"))
        except Exception as e:
            return redirect(url_for("cookies_page", msg=f"Save fail: {e}", ok="0"))
    test_results = {}
    if request.args.get("test") == "1":
        plats = [p["platform"] for p in db.get_profiles()]
        plats = [x for x in dict.fromkeys(plats) if x in TEST_URLS] or ["instagram"]
        for plat in plats:
            urls = [p["url"] for p in db.get_profiles() if p["platform"] == plat]
            ok, detail = live_cookie_test(plat, urls[0] if urls else TEST_URLS[plat])
            test_results[plat] = {"ok": ok, "detail": detail}
    return render_template("cookies.html", info=cookies_info(), msg=msg, msg_ok=msg_ok, tests=test_results)

@app.route("/cookies/delete", methods=["POST"])
def cookies_delete():
    try:
        if os.path.exists(COOKIES_PATH):
            os.remove(COOKIES_PATH)
        return redirect(url_for("cookies_page", msg="Cookies delete kar di gayin", ok="1"))
    except Exception as e:
        return redirect(url_for("cookies_page", msg=f"Delete fail: {e}", ok="0"))

@app.route("/api/metrics")
def api_metrics():
    return jsonify(db.get_metrics())

def engine_versions():
    out = {}
    try:
        from yt_dlp.version import __version__ as yv
        out["yt-dlp"] = yv
    except Exception:
        out["yt-dlp"] = "?"
    try:
        import gallery_dl
        out["gallery-dl"] = getattr(gallery_dl, "__version__", "?")
    except Exception:
        out["gallery-dl"] = "?"
    return out

def latest_release():
    """GitHub latest release (15s timeout). Returns dict or {} on fail."""
    import json
    import urllib.request
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases/latest",
            headers={"User-Agent": "CreatorWatch", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except Exception as e:
        return {"error": str(e)[:200]}

def _ver_tuple(v):
    try:
        return tuple(int(x) for x in str(v).lstrip("v").split("."))
    except Exception:
        return (0,)

@app.route("/updates", methods=["GET", "POST"])
def updates_page():
    msg, msg_ok, rel = "", False, {}
    action = request.form.get("action", "") if request.method == "POST" else ""
    if action == "check" or request.method == "GET":
        rel = latest_release()
    if action == "engines":
        if is_frozen():
            msg, msg_ok = "EXE me engines bundled hain — app update ke sath naye milenge", False
        else:
            msg, msg_ok = _upgrade_engines()
        rel = latest_release()
    if action == "app" and is_frozen():
        ok, detail = _download_update(rel or latest_release())
        msg, msg_ok = detail, ok
        rel = rel or {}
    if action == "restart" and is_frozen():
        _apply_update_restart()
        return "<h2>Update apply ho rahi hai — app restart ho rahi hai. 10 sec me dashboard kholo.</h2><a href='/'>Dashboard</a>"
    latest = (rel.get("tag_name", "") if isinstance(rel, dict) else "") or ""
    has_update = bool(latest) and _ver_tuple(latest) > _ver_tuple(VERSION)
    pending = os.path.exists(os.path.join(app_dir(), "CreatorWatch.new.exe"))
    return render_template("updates.html", version=VERSION, latest=latest or "—",
                           has_update=has_update, notes=(rel.get("body", "") or "")[:1500] if isinstance(rel, dict) else "",
                           engines=engine_versions(), frozen=is_frozen(),
                           pending=pending, msg=msg, msg_ok=msg_ok,
                           rel_error=(rel.get("error", "") if isinstance(rel, dict) else ""))

def _upgrade_engines():
    """Source mode: pip se yt-dlp + gallery-dl upgrade (engines purane hon to site fail hoti hai)."""
    import subprocess, sys
    try:
        p = subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "gallery-dl"],
                           capture_output=True, text=True, timeout=600)
        tail = (p.stdout + p.stderr)[-500:]
        if p.returncode == 0:
            return f"Engines updated: {engine_versions()}", True
        return f"Engine update fail: {tail}", False
    except Exception as e:
        return f"Engine update fail: {e}", False

def _download_update(rel):
    """Frozen: release asset (CreatorWatch.exe) download -> .new.exe."""
    import urllib.request
    try:
        assets = rel.get("assets", []) if isinstance(rel, dict) else []
        url = ""
        for a in assets:
            if str(a.get("name", "")).lower().endswith(".exe"):
                url = a.get("browser_download_url", "")
                break
        if not url:
            return False, "Release me .exe asset nahi mili"
        dest = os.path.join(app_dir(), "CreatorWatch.new.exe")
        req = urllib.request.Request(url, headers={"User-Agent": "CreatorWatch"})
        with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as f:
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
        return True, "Update download ho gayi — Restart dabao"
    except Exception as e:
        return False, f"Download fail: {e}"

def _apply_update_restart():
    """Old exe ko .new se replace karke restart (batch detached)."""
    import subprocess
    d = app_dir()
    bat = os.path.join(d, "_cw_update.bat")
    open(bat, "w").write(
        "@echo off\ntimeout /t 3 /nobreak >nul\n"
        'move /y "CreatorWatch.new.exe" "CreatorWatch.exe"\n'
        'start "" "CreatorWatch.exe"\ndel "%~f0"\n')
    subprocess.Popen(["cmd", "/c", bat], cwd=d,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    threading.Timer(2.0, lambda: os._exit(0)).start()

def start_scheduler():
    sched = BackgroundScheduler(daemon=True)
    # har 1 min me due profiles pool me submit (max limit, busy skip)
    sched.add_job(submit_due, "interval", minutes=1, id="auto_check")
    sched.start()
    return sched

if __name__ == "__main__":
    start_scheduler()
    print("Dashboard: http://127.0.0.1:5000")
    print("Downloads folder: ./downloads/")
    print(f"Workers: {max_workers()} parallel profiles (per-profile sequential)")
    if is_frozen():
        # desktop mode: same web interface, browser khud khul jaye
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
