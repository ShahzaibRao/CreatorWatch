import os
import re
from paths import app_dir, ensure_pylibs
ensure_pylibs()
import yt_dlp
from database import video_exists, add_video, update_last_check

BASE_DIR = app_dir()
DOWNLOADS_ROOT = os.path.join(BASE_DIR, "downloads")

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
    if custom:
        folder, _err = resolve_folder(custom)
        if folder:
            return folder
    from database import get_downloads_root
    root = get_downloads_root()
    try:
        os.makedirs(root, exist_ok=True)
    except Exception:
        root = os.path.join(BASE_DIR, "downloads")
        os.makedirs(root, exist_ok=True)
    folder = os.path.join(root, f"{platform}_{sanitize(name)}")
    os.makedirs(folder, exist_ok=True)
    return folder

def _ydl_opts_flat():
    # fast check: don't download, just list
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": 10,  # latest 10 only per check
        "skip_download": True,
    }
    # optional cookies for insta/tiktok if user puts cookies.txt
    ck = os.path.join(BASE_DIR, "cookies.txt")
    if os.path.exists(ck):
        opts["cookiefile"] = ck
    return opts

def fetch_latest_entries(profile_url: str):
    """Return list of {id, title, url} for latest videos (max 10)."""
    plat = detect_platform(profile_url)
    if plat == "instagram":
        return ig_fetch(profile_url, 10)  # yt-dlp insta broken -> gallery-dl
    if plat == "twitter":
        return tw_fetch(profile_url, 10)  # is yt-dlp me x.com support nahi -> gallery-dl
    profile_url = normalize_profile_url(profile_url)
    with yt_dlp.YoutubeDL(_ydl_opts_flat()) as ydl:
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
                with yt_dlp.YoutubeDL(_ydl_opts_flat()) as ydl2:
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
            tools = os.path.join(BASE_DIR, "tools")
            os.makedirs(tools, exist_ok=True)
            dest = os.path.join(tools, "ffmpeg.exe")
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
        # exe me alag python nahi — gallery-dl in-process chalao, output capture
        import io, contextlib
        from gallery_dl import __main__ as gdl_main
        out_buf, err_buf = io.StringIO(), io.StringIO()
        rc = 1
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            try:
                rc = gdl_main.main(args) or 0
            except SystemExit as e:
                try:
                    rc = int(e.code or 0)
                except (TypeError, ValueError):
                    rc = 1
            except Exception as e:
                err_buf.write(f"gallery-dl error: {e}")
                rc = 1
        class R:
            pass
        r = R()
        r.returncode, r.stdout, r.stderr = rc, out_buf.getvalue(), err_buf.getvalue()
        return r
    cmd = [sys.executable, "-m", "gallery_dl"] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          cwd=BASE_DIR, env=_env_with_ffmpeg())

def ig_fetch(profile_url: str, limit: int = 10):
    """Instagram listing gallery-dl se (yt-dlp ka insta extractor broken hai)."""
    ck = os.path.join(BASE_DIR, "cookies.txt")
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
        raise Exception("koi post nahi mili — cookies expire ho sakti hain, dobara import karo")
    return entries

def tw_fetch(profile_url: str, limit: int = 10):
    """X/Twitter listing gallery-dl se (is yt-dlp version me x.com support nahi)."""
    ck = os.path.join(BASE_DIR, "cookies.txt")
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
        raise Exception("koi tweet nahi mili — x.com login cookies chahiye, dobara import karo")
    return entries

def ig_download(post_url: str, folder: str, progress=None):
    """Instagram/X post download gallery-dl se. Returns (filepath, title)."""
    import glob
    ck = os.path.join(BASE_DIR, "cookies.txt")
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

def download_one(video_url: str, folder: str, quality: str = "720p", platform: str = "youtube", progress=None):
    """Download single video, return (filepath, title)."""
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
            progress({"pct": pct, "title": d.get("filename", "")[-60:]})
        elif progress and d.get("status") == "finished":
            progress({"pct": 100})
    opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": os.path.join(folder, "%(title).50s-%(id)s.%(ext)s"),
        "format": fmt,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "progress_hooks": [_hook],
    }
    ff = _ffmpeg()
    if ff:
        opts["ffmpeg_location"] = ff
    ck = os.path.join(BASE_DIR, "cookies.txt")
    if os.path.exists(ck):
        opts["cookiefile"] = ck
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
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
    if plat in ("instagram", "twitter") and not os.path.exists(os.path.join(BASE_DIR, "cookies.txt")):
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
        entries = fetch_latest_entries(profile["url"])
    except Exception as e:
        msg = _friendly_error(profile, f"Fetch failed: {e}")
        set_profile_error(pid, msg)
        return 0, [msg]
    if not entries:
        update_last_check(pid)
        return 0, ["Koi video nahi mili"]
    quality = profile.get("quality", "720p") or "720p"
    platform = profile.get("platform", "youtube") or "youtube"
    new_count, errors = 0, []
    latest = entries[0]  # sab se recent upload
    if not video_exists(pid, latest["id"]):
        try:
            if progress:
                progress({"stage": "downloading", "done": 0, "total": 1, "pct": 0, "title": latest["title"][:60]})
            fp, title = download_one(latest["url"], folder, quality, platform,
                                     progress=(lambda u: progress({**{"stage": "downloading", "done": 0, "total": 1}, **u})) if progress else None)
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
        entries = fetch_latest_entries(profile["url"])
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
                                     progress=(lambda u, b=base: progress({**b, **u})) if progress else None)
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
