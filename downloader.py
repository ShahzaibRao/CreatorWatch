import os
import re
import sys as _sys
import threading as _th
from paths import app_dir, ensure_pylibs, user_data_dir
ensure_pylibs()
from database import video_exists, add_video, update_last_check

class _ThreadCaptureIO:
    """Thread-local stdout/stderr proxy.

    gallery-dl in-process chalate waqt uska output capture karna hai, lekin
    contextlib.redirect_stdout GLOBAL hai — agar worker thread atak jaye to
    pure app ke print()/logs buffer me gum ho jate. Ye proxy sirf us thread
    ka output pakarta hai jisne capture() kiya ho.
    """
    def __init__(self, original):
        self._orig = original
        self._local = _th.local()
    def capture(self):
        import io
        buf = io.StringIO()
        self.register(buf)
        return buf
    def register(self, buf):
        """Kisi aur thread ke banaye hue buffer ko IS thread se joro."""
        self._local.buf = buf
    def release(self):
        self._local.buf = None
    def write(self, s):
        buf = getattr(self._local, "buf", None)
        (buf if buf is not None else self._orig).write(s)
    def writelines(self, lines):
        for line in lines:
            self.write(line)
    def flush(self):
        buf = getattr(self._local, "buf", None)
        (buf if buf is not None else self._orig).flush()
    def isatty(self):
        try:
            return self._orig.isatty()
        except Exception:
            return False
    @property
    def encoding(self):
        return getattr(self._orig, "encoding", "utf-8")
    def __getattr__(self, name):
        return getattr(self._orig, name)

# App start par hi proxy lagao taake har print thread-safe rahe
_proxy_stdout = _ThreadCaptureIO(_sys.stdout)
_proxy_stderr = _ThreadCaptureIO(_sys.stderr)
_sys.stdout, _sys.stderr = _proxy_stdout, _proxy_stderr

# gallery-dl (tools/pylibs se) ko `requests` chahiye — EXE me bundle taake
# pylibs ki halat jesi bhi ho, in-process gallery-dl hamesha chale.
# (PyInstaller isi import ki wajah se requests bundle karta hai.)
import requests  # noqa: F401

# yt-dlp (tools/pylibs se, PyInstaller me --exclude-module hai) ko ye stdlib
# modules chahiye. Explicit imports taake PyInstaller inhe EXE me bundle kare —
# warna `import yt_dlp` fail hota hai ("No module named 'optparse'").
# (Source mode me system Python me ye pehle se hote hain; sirf frozen EXE ke liye.)
# NOTE: submodules (html.parser jese) alag se import karne parte hain — sirf
# top-level (html) bundle hone se kaam nahi chalta.
import bisect  # noqa: F401
import calendar  # noqa: F401
import fileinput  # noqa: F401
import getpass  # noqa: F401
import heapq  # noqa: F401
import netrc  # noqa: F401
import optparse  # noqa: F401
import plistlib  # noqa: F401
import quopri  # noqa: F401
import secrets  # noqa: F401
import shlex  # noqa: F401
import collections.abc  # noqa: F401
import concurrent.futures  # noqa: F401
import email.header  # noqa: F401
import email.message  # noqa: F401
import email.utils  # noqa: F401
import html.entities  # noqa: F401
import html.parser  # noqa: F401
import http.client  # noqa: F401
import http.cookiejar  # noqa: F401
import http.cookies  # noqa: F401
import http.server  # noqa: F401
import importlib.abc  # noqa: F401
import importlib.machinery  # noqa: F401
import importlib.resources  # noqa: F401
import importlib.util  # noqa: F401
import urllib.error  # noqa: F401
import urllib.parse  # noqa: F401
import urllib.request  # noqa: F401
import urllib.response  # noqa: F401
import xml.etree.ElementTree  # noqa: F401
try:
    import msvcrt  # noqa: F401  (Windows-only)
    import ctypes.wintypes  # noqa: F401  (Windows-only)
except ImportError:
    pass
try:
    import fcntl  # noqa: F401  (Unix-only)
    import pty  # noqa: F401  (Unix-only)
except ImportError:
    pass

def _yt_dlp():
    """Lazy import taake EXE lightweight rahe — engines Updates page se install hote hain."""
    try:
        import yt_dlp as _y
        return _y
    except ImportError:
        raise Exception("yt-dlp installed nahi — Updates page par 'Install Required Packages' dabao")

BASE_DIR = app_dir()          # program/tools: install folder (EXE ke sath rehte hain)
DATA_DIR = user_data_dir()  # user data: %APPDATA%/CreatorWatch (uninstall-safe)
DOWNLOADS_ROOT = os.path.join(DATA_DIR, "downloads")

def detect_platform(url: str) -> str:
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

def normalize_profile_url(url: str) -> str:
    """x.com -> twitter.com (yt-dlp), YouTube channel root -> /videos tab."""
    u = url.strip().rstrip("/")
    low = u.lower()
    if "x.com/" in low:
        u = u.replace("x.com/", "twitter.com/").replace("X.com/", "twitter.com/")
        low = u.lower()
    if ("youtube.com/@" in low or "/channel/" in low or "/c/" in low or "/user/" in low):
        if not any(x in low for x in ["/videos", "/shorts", "/watch", "/playlist", "/streams"]):
            return u + "/videos"
    return u

def sanitize(name: str) -> str:
    name = name.strip().replace(" ", "_")
    return re.sub(r"[^\w\-]", "", name)[:50] or "prospect"

def resolve_folder(custom):
    """User di hui location (absolute/relative/drive) validate karke wapas. Fail -> (None, reason)."""
    c = (custom or "").strip().strip('"')
    if not c:
        return None, ""
    if not os.path.isabs(c):
        c = os.path.join(BASE_DIR, c)
    try:
        os.makedirs(c, exist_ok=True)
    except Exception as e:
        return None, str(e)[:150]
    if not os.path.isdir(c):
        return None, "folder nahi bana"
    return os.path.abspath(c), ""

def prospect_folder(name: str, platform: str, custom: str = "") -> str:
    """Style: <root>/<platform>/<creator>/ — purane platform_name wale folders DB me wese hi rehte hain."""
    base = ""
    if custom:
        base, _err = resolve_folder(custom)
    if not base:
        from database import get_downloads_root
        base = get_downloads_root()
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        base = os.path.join(DATA_DIR, "downloads")
        os.makedirs(base, exist_ok=True)
    folder = os.path.join(base, platform, sanitize(name))
    os.makedirs(folder, exist_ok=True)
    return folder

def _qjs_path():
    """QuickJS (n-challenge solver). Windows: bundled vendor; Linux: system qjs."""
    import sys as _sys
    if _sys.platform != "win32":
        import shutil
        return shutil.which("qjs") or ""
    try:
        base = _sys._MEIPASS
    except AttributeError:
        base = BASE_DIR
    p = os.path.join(base, "vendor", "qjs.exe")
    return p if os.path.exists(p) else ""

POT_PORT = 4416
POT_URL = f"http://127.0.0.1:{POT_PORT}"

def _deno_exe():
    import sys as _sys
    exe = "deno.exe" if _sys.platform == "win32" else "deno"
    for c in (os.path.join(BASE_DIR, "tools", "deno", exe),
              os.path.join(BASE_DIR, "tools", "deno-full", exe)):
        if os.path.exists(c):
            return c
    return ""

def _pot_dir():
    for c in (os.path.join(BASE_DIR, "tools", "potserver"),
              os.path.join(BASE_DIR, "bgutil-server")):
        if os.path.isdir(os.path.join(c, "src")):
            return c
    return ""

def _js_runtimes(prefer_deno=False):
    runtimes = {}
    d = _deno_exe()
    if d:
        runtimes["deno"] = {"path": d}
    q = _qjs_path()
    if q:
        runtimes["quickjs"] = {"path": q}
    if not runtimes:
        runtimes = {"deno": {}}
    if prefer_deno and "deno" in runtimes:
        runtimes = {"deno": runtimes["deno"], **{k: v for k, v in runtimes.items() if k != "deno"}}
    return runtimes

def _yt_proxy():
    try:
        from database import get_setting
        return (get_setting("yt_proxy", "") or "").strip()
    except Exception:
        return ""

def _yt_opts(pot=False):
    """YouTube opts: cookies + JS runtime + (pot: PO token + EJS solver) + proxy."""
    o = {"js_runtimes": _js_runtimes(prefer_deno=pot)}
    ck = os.path.join(DATA_DIR, "cookies.txt")
    if os.path.exists(ck):
        o["cookiefile"] = ck
    px = _yt_proxy()
    if px:
        o["proxy"] = px
    if pot:
        o["remote_components"] = {"ejs:github"}
        o["extractor_args"] = {"youtube": {"po_token": ["web.player+bgutil:http"]}}
    return o

def pot_running():
    import urllib.request
    try:
        with urllib.request.urlopen(POT_URL + "/ping", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False

def start_pot_server(progress=None):
    """bgutil POT server (deno) background me — ek hi instance."""
    import subprocess
    import sys as _sys
    import urllib.request
    if pot_running():
        return True
    d = _deno_exe()
    pdir = _pot_dir()
    main = os.path.join(pdir, "src", "main.ts") if pdir else ""
    if not d or not main or not os.path.exists(main):
        return False
    try:
        logf = open(os.path.join(pdir, "server.log"), "a")
    except Exception:
        logf = subprocess.DEVNULL

    def _pg(title):
        if progress:
            try:
                progress({"title": title, "pct": None})
            except Exception:
                pass

    # npm deps: deno install (node_modules) — bina iske "Could not resolve express"
    # dobara install jab: marker nahi, ya node_modules dir hi nahi (delete/partial)
    nm_dir = os.path.join(pdir, "node_modules")
    nm_ok = os.path.join(nm_dir, ".install_ok")

    def _mark_install_ok():
        # /ping hi ground truth hai — server chal para to deps theek hain
        try:
            os.makedirs(nm_dir, exist_ok=True)
            with open(nm_ok, "w") as fh:
                fh.write("ok")
        except Exception:
            pass

    if not (os.path.exists(nm_ok) and os.path.isdir(nm_dir)):
        _pg("POT server: npm packages install ho rahe hain (deno install)…")
        ok_install = False
        try:
            kw_i = dict(cwd=pdir, stdout=logf, stderr=subprocess.STDOUT)
            if os.name == "nt":
                kw_i["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            # --min-dep-age 0: deno ki 24h "minimum dependency age" policy
            # taaza npm versions ko block karti hai — isay off karo
            r = subprocess.run([d, "install", "--min-dep-age", "0"], timeout=900, **kw_i)
            ok_install = (r.returncode == 0)
        except Exception as e:
            try:
                logf.write(f"[deno install fail] {e}\n")
                logf.flush()
            except Exception:
                pass
        if ok_install:
            _mark_install_ok()
        else:
            try:
                logf.write("[deno install] FAILED — agli dafa dobara try hoga\n")
                logf.flush()
            except Exception:
                pass
    try:
        kw = dict(cwd=pdir, stdout=logf, stderr=subprocess.STDOUT)
        if os.name == "nt":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([d, "run", "--allow-all", "src/main.ts", "--port", str(POT_PORT)], **kw)
        for _ in range(30):
            try:
                with urllib.request.urlopen(POT_URL + "/ping", timeout=2) as r:
                    if r.status == 200:
                        _mark_install_ok()
                        return True
            except Exception:
                pass
            import time as _t
            _t.sleep(1)
    except Exception:
        pass
    if pot_running():
        _mark_install_ok()
        return True
    return False

WALL_HINTS = ("Sign in to confirm", "not a bot", "needs to be reloaded")

def is_wall_error(err):
    s = str(err)
    return any(h in s for h in WALL_HINTS)

DENO_URL = "https://github.com/denoland/deno/releases/download/v2.9.7/deno-x86_64-pc-windows-msvc.zip"
POT_RAW = "https://raw.githubusercontent.com/Brainicism/bgutil-ytdlp-pot-provider/master/server"
POT_FILES = ["src/generate_once.ts", "src/main.ts", "src/session_manager.ts",
             "src/utils.ts", "scripts/check_lockfiles.ts", "deno.json", "package.json"]

def yt_stack_status():
    """Deno + POT server source mojood? Returns dict."""
    d = _deno_exe()
    pdir = _pot_dir()
    return {"deno": bool(d), "potserver": bool(pdir),
            "server_running": pot_running() if (d and pdir) else False}

def _dl(url, progress, title, pct0, pct1, timeout=900):
    """Download with progress callbacks {"title", "pct"}. Returns bytes."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "CreatorWatch"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        total = int(r.headers.get("Content-Length") or 0)
        got, chunks = 0, []
        while True:
            ch = r.read(1024 * 256)
            if not ch:
                break
            chunks.append(ch)
            got += len(ch)
            if progress and total:
                try:
                    progress({"title": title,
                              "pct": int(pct0 + (pct1 - pct0) * got / total)})
                except Exception:
                    pass
    return b"".join(chunks)


def ensure_yt_stack(progress=None):
    """Deno (~40MB ek bar) + POT server source download -> tools/. Returns (ok, report)."""
    import zipfile
    import io as _io

    def _pg(title, pct=None):
        if progress:
            try:
                progress({"title": title, "pct": pct})
            except Exception:
                pass

    notes = []
    dd = os.path.join(BASE_DIR, "tools", "deno")
    dexe = os.path.join(dd, "deno.exe")
    if not os.path.exists(dexe):
        try:
            _pg("Deno download (~40MB)…", 0)
            blob = _dl(DENO_URL, progress, "Deno download (~40MB)…", 0, 45)
            os.makedirs(dd, exist_ok=True)
            with zipfile.ZipFile(_io.BytesIO(blob)) as z:
                z.extractall(dd)
            notes.append("deno ok")
        except Exception as e:
            return False, f"deno download fail: {e}"
    else:
        notes.append("deno pehle se")
    pdir = os.path.join(BASE_DIR, "tools", "potserver")
    missing = [f for f in POT_FILES if not os.path.exists(os.path.join(pdir, f))]
    if missing:
        try:
            n = len(missing)
            for i, f in enumerate(missing):
                _pg(f"POT server files… ({i + 1}/{n})", 45 + int(40 * i / n))
                data = _dl(f"{POT_RAW}/{f}", None, "", 0, 0, timeout=120)
                dest = os.path.join(pdir, f)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as fh:
                    fh.write(data)
            notes.append("potserver files ok")
            if "package.json" in missing:
                # deps badal sakti hain — install dobara ho
                try:
                    os.remove(os.path.join(pdir, "node_modules", ".install_ok"))
                except Exception:
                    pass
        except Exception as e:
            return False, f"potserver download fail: {e}"
    else:
        notes.append("potserver pehle se")
    _pg("Server start ho raha hai… (pehli boot me npm download ki wajah se 1-2 min lag sakta hai)", 95)
    ok = start_pot_server(progress=progress)
    notes.append("server running" if ok else "server start FAIL — tools/potserver/server.log dekho")
    return ok, "; ".join(notes)

def _ydl_opts_flat():
    # fast check: don't download, just list
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": 10,  # latest 10 only per check
        "skip_download": True,
    }
    opts.update(_yt_opts())
    return opts

def detect_scope(url: str) -> str:
    """Link type se scope: channel -> both, shorts link -> shorts, video link -> videos."""
    low = (url or "").lower()
    if "youtube.com" not in low and "youtu.be" not in low:
        return "both"
    if "/shorts" in low:
        return "shorts"
    if "/videos" in low or "/streams" in low:
        return "videos"
    if "/watch" in low or "youtu.be/" in low or "/live/" in low:
        return "videos"
    return "both"  # channel root

def _yt_base(url: str):
    """Kisi bhi YouTube link se channel root nikalo. Returns (base, is_channel)."""
    u = url.strip().rstrip("/")
    m = re.search(r"(https?://(?:www\.)?youtube\.com/(?:@[^/?#]+|channel/[^/?#]+|c/[^/?#]+|user/[^/?#]+))", u, re.I)
    if m:
        return m.group(1), True
    try:
        with _yt_dlp().YoutubeDL({**{"quiet": True, "no_warnings": True, "skip_download": True}, **_yt_opts()}) as ydl:
            info = ydl.extract_info(u, download=False) or {}
        for k in ("channel_url", "uploader_url"):
            v = info.get(k) or ""
            if "youtube.com" in v:
                return v.rstrip("/"), True
        chid = info.get("channel_id")
        if chid:
            return f"https://www.youtube.com/channel/{chid}", True
    except Exception:
        pass
    return u, False

def fetch_latest_entries(profile_url: str, scope: str = "both"):
    """Return list of {id, title, url} for latest (max 10). Scope: both/videos/shorts."""
    plat = detect_platform(profile_url)
    if plat == "instagram":
        return ig_fetch(profile_url, 10)  # yt-dlp insta broken -> gallery-dl
    if plat == "twitter":
        return tw_fetch(profile_url, 10)  # is yt-dlp me x.com support nahi -> gallery-dl
    if scope not in ("both", "videos", "shorts"):
        scope = "both"
    if plat == "youtube":
        base, is_ch = _yt_base(profile_url)
        if is_ch:
            tabs = {"both": ["videos", "shorts"], "videos": ["videos"], "shorts": ["shorts"]}[scope]
            entries, seen = [], set()
            for tab in tabs:
                try:
                    with _yt_dlp().YoutubeDL(_ydl_opts_flat()) as ydl:
                        tinfo = ydl.extract_info(f"{base}/{tab}", download=False)
                    for e in ((tinfo or {}).get("entries") or []):
                        if not e or not e.get("id"):
                            continue
                        vid = e["id"]
                        if vid.startswith("UC") or vid.startswith("PL") or vid in seen:
                            continue
                        seen.add(vid)
                        entries.append({
                            "id": vid,
                            "title": e.get("title", vid),
                            "url": e.get("url") or e.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}",
                        })
                        if len(entries) >= 10:
                            break
                except Exception:
                    continue
                if len(entries) >= 10:
                    break
            return entries[:10]
    profile_url = normalize_profile_url(profile_url)
    with _yt_dlp().YoutubeDL(_ydl_opts_flat()) as ydl:
        info = ydl.extract_info(profile_url, download=False)
    entries = []
    if not info:
        return entries
    # single video case
    if info.get("_type") != "playlist" and "id" in info:
        entries = [{"id": info["id"], "title": info.get("title", info["id"]),
                    "url": info.get("webpage_url", profile_url)}]
        return entries

    raw = [e for e in (info.get("entries") or []) if e]

    # YouTube channel tabs case: entries are tabs (/videos, /shorts) not videos.
    # Detect: entry URL contains /videos, /shorts, /streams, /releases
    tab_entries = [e for e in raw if any(
        t in str(e.get("url", "") or e.get("webpage_url", "") or e.get("title", "")).lower()
        for t in ["/videos", "/shorts", "/streams", "/releases"]
    )]
    # fallback: if ids look like channel IDs (start with UC) -> treat as tabs
    if not tab_entries and raw and all(str(e.get("id", "")).startswith("UC") for e in raw[:3]):
        tab_entries = raw

    if tab_entries:
        # videos tab ko prefer karo, warna pehla tab
        def tab_key(e):
            u = str(e.get("url", "") or e.get("webpage_url", "")).lower()
            if "/videos" in u:
                return 0
            if "/shorts" in u:
                return 1
            return 2
        tab_entries.sort(key=tab_key)
        for tab in tab_entries[:2]:  # videos + shorts dono check karo
            tab_url = tab.get("url") or tab.get("webpage_url")
            if not tab_url:
                continue
            try:
                with _yt_dlp().YoutubeDL(_ydl_opts_flat()) as ydl2:
                    tinfo = ydl2.extract_info(tab_url, download=False)
                for e in (tinfo.get("entries") or []):
                    if not e or not e.get("id"):
                        continue
                    vid = e["id"]
                    # nested playlist skip
                    if vid.startswith("UC") or vid.startswith("PL"):
                        continue
                    entries.append({
                        "id": vid,
                        "title": e.get("title", vid),
                        "url": e.get("url") or e.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}",
                    })
                    if len(entries) >= 10:
                        break
            except Exception:
                continue
            if len(entries) >= 5:
                break
        return entries[:10]

    for e in raw:
        if not e:
            continue
        vid = e.get("id")
        if not vid:
            continue
        entries.append({
            "id": vid,
            "title": e.get("title", vid),
            "url": e.get("url") or e.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}",
        })
    return entries[:10]

def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def _env_with_ffmpeg():
    """gallery-dl subprocess ke liye ffmpeg.exe PATH me (merge ke liye)."""
    import shutil
    env = dict(os.environ)
    try:
        ff = _ffmpeg()
        if ff and os.path.exists(ff):
            import sys as _sys
            tools = os.path.join(BASE_DIR, "tools")
            os.makedirs(tools, exist_ok=True)
            dest = os.path.join(tools, "ffmpeg.exe" if _sys.platform == "win32" else "ffmpeg")
            if not os.path.exists(dest):
                shutil.copyfile(ff, dest)
            env["PATH"] = tools + os.pathsep + env.get("PATH", "")
    except Exception:
        pass
    return env

def _gdl(args, timeout=300):
    import subprocess, sys
    from paths import is_frozen
    if is_frozen():
        # exe me alag python nahi — gallery-dl in-process chalao, output capture.
        # NOTE: gallery_dl.__main__ me main() nahi hota (sirf `if __name__ ==
        # "__main__"` guard hai) — asal entry point gallery_dl.main() hai jo
        # sys.argv se args parhta hai.
        # Thread + timeout: gallery-dl network par atak jaye (x.com slow/hang)
        # to worker hamesha ke liye block na ho.
        import io, threading
        import gallery_dl
        out_buf, err_buf = io.StringIO(), io.StringIO()
        rc = [1]
        old_argv = sys.argv
        sys.argv = ["gallery-dl"] + list(args)
        def _run():
            # buffer isi (worker) thread se register — thread-local hai
            _proxy_stdout.register(out_buf)
            _proxy_stderr.register(err_buf)
            try:
                try:
                    rc[0] = gallery_dl.main() or 0
                except SystemExit as e:
                    try:
                        rc[0] = int(e.code or 0)
                    except (TypeError, ValueError):
                        rc[0] = 1
                except Exception as e:
                    err_buf.write(f"gallery-dl error: {e}")
                    rc[0] = 1
            finally:
                sys.argv = old_argv
                _proxy_stdout.release()
                _proxy_stderr.release()
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout)
        class R:
            pass
        r = R()
        if t.is_alive():
            # worker atak gaya — uska buffer release ho chuka hoga ya hoga;
            # main thread ke prints mehfooz (proxy thread-local hai)
            _proxy_stdout.release()
            _proxy_stderr.release()
            r.returncode, r.stdout = 1, out_buf.getvalue()
            r.stderr = (err_buf.getvalue() + f"\ngallery-dl timeout ({timeout}s) — x.com/network atak gaya").strip()
        else:
            r.returncode, r.stdout, r.stderr = rc[0], out_buf.getvalue(), err_buf.getvalue()
        return r
    cmd = [sys.executable, "-m", "gallery_dl"] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          cwd=BASE_DIR, env=_env_with_ffmpeg())

def ig_fetch(profile_url: str, limit: int = 10):
    """Instagram listing gallery-dl se (yt-dlp ka insta extractor broken hai)."""
    ck = os.path.join(DATA_DIR, "cookies.txt")
    if not os.path.exists(ck):
        raise Exception("Instagram ke liye login chahiye — /cookies page par cookies import karo")
    p = _gdl(["--cookies", ck, "--range", f"1-{limit * 2}", "--no-mtime",
              "--print", "{shortcode} :: {post_url} :: {date} :: {caption}",
              profile_url.rstrip("/") + "/"])
    if p.returncode != 0:
        raise Exception((p.stderr.strip() or "gallery-dl failed")[:250])
    entries, seen = [], set()
    for line in p.stdout.splitlines():
        parts = line.split(" :: ")
        if len(parts) < 3 or not parts[0].strip() or not parts[1].strip():
            continue
        sc, url = parts[0].strip(), parts[1].strip()
        if url in seen:
            continue
        seen.add(url)
        title = (parts[3] if len(parts) > 3 else "").strip()[:80] or sc
        entries.append({"id": sc, "title": title, "url": url})
        if len(entries) >= limit:
            break
    if not entries:
        dbg = (p.stderr.strip() or p.stdout.strip())[:250]
        raise Exception(f"koi post nahi mili [{dbg}] — cookies expire ho sakti hain, dobara import karo")
    return entries

def tw_fetch(profile_url: str, limit: int = 10):
    """X/Twitter listing gallery-dl se (is yt-dlp version me x.com support nahi)."""
    ck = os.path.join(DATA_DIR, "cookies.txt")
    if not os.path.exists(ck):
        raise Exception("X (Twitter) ke liye login chahiye — /cookies page par x.com cookies import karo")
    url = normalize_profile_url(profile_url)
    p = _gdl(["--cookies", ck, "--range", f"1-{limit * 2}", "--no-mtime",
              "--print", "{tweet_id} :: {date} :: {content}", url])
    if p.returncode != 0:
        err = (p.stderr.strip() or "gallery-dl failed")[:250]
        if "AuthRequired" in err or "authenticated" in err:
            err += " — x.com par login cookies (auth_token) chahiye, dobara import karo"
        raise Exception(err)
    entries, seen = [], set()
    for line in p.stdout.splitlines():
        parts = line.split(" :: ")
        if len(parts) < 2:
            continue
        tid = parts[0].strip()
        if not tid or not tid[0].isdigit() or tid in seen:
            continue
        seen.add(tid)
        title = (" ".join(parts[2:]).strip()[:80] if len(parts) > 2 else tid) or tid
        entries.append({"id": tid, "title": title, "url": f"https://x.com/i/status/{tid}"})
        if len(entries) >= limit:
            break
    if not entries:
        dbg = (p.stderr.strip() or p.stdout.strip())[:250]
        raise Exception(f"koi tweet nahi mili [{dbg}] — x.com login cookies check karo, dobara import karo")
    return entries

def ig_download(post_url: str, folder: str, progress=None):
    """Instagram/X post download gallery-dl se. Returns (filepath, title)."""
    import glob
    ck = os.path.join(DATA_DIR, "cookies.txt")
    os.makedirs(folder, exist_ok=True)
    if progress:
        progress({"pct": None, "title": "gallery-dl download..."})
    before = {f for f in glob.glob(os.path.join(folder, "**", "*"), recursive=True)}
    p = _gdl(["--cookies", ck, "-d", folder, "--no-mtime", post_url], timeout=600)
    if p.returncode != 0:
        raise Exception((p.stderr.strip() or "gallery-dl download failed")[:250])
    after = [f for f in glob.glob(os.path.join(folder, "**", "*"), recursive=True)
             if f not in before and os.path.isfile(f)]
    if not after:
        return folder, post_url
    after.sort(key=lambda f: (os.path.getsize(f), os.path.getmtime(f)), reverse=True)
    return after[0], os.path.basename(after[0])

QUALITY_FORMATS = {
    # ffmpeg ab bundled hai -> merge wale formats chalenge
    "best": "bv*+ba/b",
    "1080p": "bv*[height<=1080]+ba/b[height<=1080]",
    "720p": "bv*[height<=720]+ba/b[height<=720]",
    "480p": "bv*[height<=480]+ba/b[height<=480]",
    "360p": "bv*[height<=360]+ba/b[height<=360]",
}

def download_one(video_url: str, folder: str, quality: str = "720p", platform: str = "youtube", progress=None, method: str = "auto"):
    """Download single video, return (filepath, title). YouTube: auto = direct, wall par PO-token retry."""
    if platform in ("instagram", "twitter"):
        return ig_download(video_url, folder, progress)
    if platform == "tiktok":
        fmt = "best/b"  # tiktok par single-file best (height filter support nahi)
    else:
        fmt = QUALITY_FORMATS.get(quality, QUALITY_FORMATS["720p"])
    def _hook(d):
        if progress and d.get("status") == "downloading":
            try:
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes", 0)
                pct = round(done * 100 / total, 1) if total else None
            except Exception:
                pct = None
            progress({"pct": pct, "speed": d.get("speed"), "title": d.get("filename", "")[-60:]})
        elif progress and d.get("status") == "finished":
            progress({"pct": 100, "speed": None})
    opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": os.path.join(folder, "%(title).50s-%(id)s.%(ext)s"),
        "format": fmt,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "progress_hooks": [_hook],
    }
    opts.update(_yt_opts())
    ff = _ffmpeg()
    if ff:
        opts["ffmpeg_location"] = ff
    use_pot = (platform == "youtube" and method in ("auto", "po"))
    if use_pot and method == "po":
        if not start_pot_server():
            raise Exception("PO-token server start nahi hua — Updates > Setup YouTube se install karo")
        opts.update(_yt_opts(pot=True))
    try:
        ydl = _yt_dlp().YoutubeDL(opts)
        info = ydl.extract_info(video_url, download=True)
    except Exception as e:
        if platform == "youtube" and method == "auto" and is_wall_error(e):
            if not start_pot_server():
                raise Exception(str(e)[:250] + " [YouTube wall: Updates > Setup YouTube se PO-token install karo, ya IP badlo (hotspot/VPN)]")
            opts.update(_yt_opts(pot=True))
            ydl = _yt_dlp().YoutubeDL(opts)
            info = ydl.extract_info(video_url, download=True)
        else:
            raise
    fp = ydl.prepare_filename(info)
    # mp4 merge may change ext
    if not os.path.exists(fp):
        base = os.path.splitext(fp)[0]
        for ext in (".mp4", ".mkv", ".webm"):
            if os.path.exists(base + ext):
                fp = base + ext
                break
    return fp, info.get("title", info.get("id"))

LOGIN_HINT = " (Login/cookies required: /cookies page par cookies import karo)"

def _friendly_error(profile: dict, err: str) -> str:
    plat = (profile.get("platform") or "").lower()
    if plat in ("instagram", "twitter") and not os.path.exists(os.path.join(DATA_DIR, "cookies.txt")):
        return err[:250] + LOGIN_HINT
    return err[:300]

def first_run(profile: dict, progress=None):
    """
    Pehli bar link add ho to SIRF sab se latest 1 video download,
    baqi purani sari ko 'skipped' mark (kabhi download nahi hongi).
    Uske baad har check me sirf bilkul nayi uploads download hongi.
    """
    from database import set_profile_error, mark_seen
    pid = profile["id"]
    folder = profile["folder"]
    os.makedirs(folder, exist_ok=True)
    if progress:
        progress({"stage": "listing", "done": 0, "total": 1, "pct": None, "title": "latest dhoond rahe hain..."})
    try:
        entries = fetch_latest_entries(profile["url"], profile.get("scope", "both") or "both")
    except Exception as e:
        msg = _friendly_error(profile, f"Fetch failed: {e}")
        set_profile_error(pid, msg)
        return 0, [msg]
    if not entries:
        update_last_check(pid)
        return 0, ["Koi video nahi mili"]
    quality = profile.get("quality", "720p") or "720p"
    platform = profile.get("platform", "youtube") or "youtube"
    method = profile.get("method", "auto") or "auto"
    new_count, errors = 0, []
    latest = entries[0]  # sab se recent upload
    if not video_exists(pid, latest["id"]):
        try:
            if progress:
                progress({"stage": "downloading", "done": 0, "total": 1, "pct": 0, "title": latest["title"][:60]})
            fp, title = download_one(latest["url"], folder, quality, platform,
                                     progress=(lambda u: progress({**{"stage": "downloading", "done": 0, "total": 1}, **u})) if progress else None,
                                     method=method)
            if fp == folder:
                mark_seen(pid, latest["id"], title or latest["title"])
            else:
                size = os.path.getsize(fp) if os.path.exists(fp) else 0
                add_video(pid, latest["id"], title or latest["title"], fp, size)
                new_count = 1
            if progress:
                progress({"stage": "downloading", "done": 1, "total": 1, "pct": 100, "title": title or latest["title"]})
        except Exception as ex:
            errors.append(f"{latest['id']}: {ex}")
    for e in entries[1:]:
        mark_seen(pid, e["id"], e.get("title", ""))
    if errors and new_count == 0:
        set_profile_error(pid, "; ".join(errors[:3]))
    else:
        update_last_check(pid)
    return new_count, errors

def check_profile(profile: dict, progress=None):
    """
    profile: dict with id, url, folder
    Latest 10 (videos + shorts) check karta hai, sirf NAYI download.
    DB me video_id save rehta hai -> file delete bhi ho jaye to dobara download NAHI hogi.
    Returns (new_count, errors)
    """
    from database import set_profile_error
    pid = profile["id"]
    folder = profile["folder"]
    os.makedirs(folder, exist_ok=True)
    if progress:
        progress({"stage": "listing", "done": 0, "total": 1, "pct": None, "title": "check ho raha hai..."})
    try:
        entries = fetch_latest_entries(profile["url"], profile.get("scope", "both") or "both")
    except Exception as e:
        msg = _friendly_error(profile, f"Fetch failed: {e}")
        set_profile_error(pid, msg)
        return 0, [msg]
    if not entries:
        msg = _friendly_error(profile, "Koi video nahi mili (profile empty ya login required)")
        set_profile_error(pid, msg)
        return 0, [msg]

    fresh = [e for e in entries if not video_exists(pid, e["id"])]
    new_count = 0
    errors = []
    quality = profile.get("quality", "720p") or "720p"
    platform = profile.get("platform", "youtube") or "youtube"
    method = profile.get("method", "auto") or "auto"
    total = max(len(fresh), 1)
    for i, e in enumerate(fresh):
        vid = e["id"]
        # DB check: pehle download ho chuki to skip (file delete ho tab bhi skip)
        if video_exists(pid, vid):
            continue
        try:
            base = {"stage": "downloading", "done": i, "total": total}
            if progress:
                progress({**base, "pct": 0, "title": e["title"][:60]})
            fp, title = download_one(e["url"], folder, quality, platform,
                                     progress=(lambda u, b=base: progress({**b, **u})) if progress else None,
                                     method=method)
            if fp == folder:
                # text-only post (koi media nahi) — skip mark taake retry loop na ho
                from database import mark_seen
                mark_seen(pid, vid, title or e["title"])
                continue
            size = os.path.getsize(fp) if os.path.exists(fp) else 0
            add_video(pid, vid, title or e["title"], fp, size)
            new_count += 1
            if progress:
                progress({**base, "done": i + 1, "pct": 100, "title": title or e["title"]})
        except Exception as ex:
            errors.append(f"{vid}: {ex}")
    if errors and new_count == 0:
        set_profile_error(pid, "; ".join(errors[:3]))
    else:
        update_last_check(pid)
    return new_count, errors

def check_all_profiles():
    from database import get_profiles
    results = []
    for p in get_profiles():
        if p.get("status") != "active":
            continue
        n, errs = check_profile(p)
        results.append({"profile": p["name"], "new": n, "errors": errs})
    return results

def check_due_profiles():
    """Sirf un profiles ko check karo jinka time period guzar gaya ho."""
    from database import get_due_profiles
    results = []
    for p in get_due_profiles():
        print(f"[AUTO] due: {p['name']} (har {p.get('interval_minutes',15)} min)", flush=True)
        n, errs = check_profile(p)
        results.append({"profile": p["name"], "new": n, "errors": errs})
    return results
