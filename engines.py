"""Download engines (yt-dlp / gallery-dl) — source me pip se, EXE me tools/pylibs me alag se.
Taake engine purana hone par app rukay nahi: user manually update kar sakta hai."""
import io
import json
import os
import shutil
import urllib.request
import zipfile

from paths import app_dir

ENGINES = ("yt-dlp", "gallery-dl")
# ffmpeg alag hai — ye Python package nahi, binary hai. imageio-ffmpeg ke
# wheel se binary nikal kar tools/ me rakhenge. User khud update kar sakega.
FFMPEG_PKG = "imageio-ffmpeg"
PYPI = "https://pypi.org/pypi/{pkg}/json"
UA = {"User-Agent": "CreatorWatch", "Accept": "application/json"}


def pylibs_dir():
    d = os.path.join(app_dir(), "tools", "pylibs")
    os.makedirs(d, exist_ok=True)
    return d


def _ffmpeg_exe_name():
    import sys
    return "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def _ffmpeg_tools_path():
    """tools/ffmpeg.exe — user ne Update Engines se install kiya ho to."""
    return os.path.join(app_dir(), "tools", _ffmpeg_exe_name())


def _ffmpeg_version_file():
    return os.path.join(app_dir(), "tools", "ffmpeg.version")


def ffmpeg_active_version():
    """Kaun sa ffmpeg use hoga: tools/ wala (user-updated) ya bundled ya system."""
    tp = _ffmpeg_tools_path()
    if os.path.exists(tp):
        try:
            with open(_ffmpeg_version_file()) as f:
                return f.read().strip() or "ext"
        except Exception:
            return "ext"
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        if ff and os.path.exists(ff):
            return "bundled"
    except Exception:
        pass
    import shutil
    if shutil.which("ffmpeg"):
        return "system"
    return "?"


def active_versions():
    out = {}
    # Engine update ke baad nayi files foran nazar aayen — Python failed
    # imports ka negative result cache kar leta hai (FileFinder), is liye
    # har check se pehle cache saaf karo. Warna update ke baad bhi "?" rehta.
    # AUR: pip upgrade ke baad purana loaded module hatao taake naya version aaye.
    try:
        import importlib, sys
        importlib.invalidate_caches()
        for mod in ["yt_dlp", "yt_dlp.version", "gallery_dl"]:
            sys.modules.pop(mod, None)
    except Exception:
        pass
    try:
        from yt_dlp.version import __version__ as yv
        out["yt-dlp"] = yv
    except Exception as e:
        out["yt-dlp"] = "?"
        out["yt-dlp-error"] = f"{type(e).__name__}: {e}"[:300]
    try:
        import gallery_dl
        out["gallery-dl"] = getattr(gallery_dl, "__version__", "?")
    except Exception as e:
        out["gallery-dl"] = "?"
        out["gallery-dl-error"] = f"{type(e).__name__}: {e}"[:300]
    out["ffmpeg"] = ffmpeg_active_version()
    return out


def external_versions():
    """tools/pylibs me kaun se engine versions hain (dist-info se)."""
    import glob
    out = {}
    for dist in glob.glob(os.path.join(pylibs_dir(), "*.dist-info")):
        base = os.path.basename(dist)
        if base.endswith(".dist-info"):
            base = base[:-len(".dist-info")]
        if "-" in base:
            name, ver = base.split("-", 1)
            out[name.replace("_", "-")] = ver
    return out


def latest_pypi(pkg):
    req = urllib.request.Request(PYPI.format(pkg=pkg), headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    ver = data["info"]["version"]
    wheel_url = ""
    for u in data.get("urls", []):
        if u.get("packagetype") == "bdist_wheel" and "py3-none-any" in u.get("filename", ""):
            wheel_url = u["url"]
            break
    if not wheel_url:
        for u in data.get("urls", []):
            if u.get("packagetype") == "bdist_wheel":
                wheel_url = u["url"]
                break
    return ver, wheel_url


def _download_blob(url, on_chunk=None, tries=3):
    """Download with retry + stall detection.

    Har read-operation par 45s socket timeout — connection atak jaye to
    hamesha latka nahi rehta, retry hota hai. (Pehle timeout=600 tha.)
    """
    import time
    import socket
    last_err = None
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CreatorWatch"})
            with urllib.request.urlopen(req, timeout=45) as r:
                total = int(r.headers.get("Content-Length") or 0)
                got, chunks = 0, []
                t0 = time.monotonic()
                while True:
                    try:
                        ch = r.read(1024 * 64)
                    except (socket.timeout, TimeoutError):
                        raise Exception("connection atak gayi (45s stall)")
                    if not ch:
                        break
                    chunks.append(ch)
                    got += len(ch)
                    if total and on_chunk:
                        on_chunk(got, total)
                    if time.monotonic() - t0 > 900:  # 15 min cap
                        raise Exception("download bohat slow (15 min)")
            blob = b"".join(chunks)
            if not blob:
                raise Exception("khaali download mili")
            if total and got != total:
                raise Exception(f"download adhoora ({got}/{total} bytes)")
            return blob
        except Exception as e:
            last_err = e
            if attempt < tries:
                time.sleep(2 * attempt)  # 2s, 4s backoff
    raise last_err


def _friendly_dl_error(e):
    s = str(e)
    if "getaddrinfo failed" in s or "11001" in s or "Name or service not known" in s:
        return "internet/DNS masla (site resolve nahi hui) — thori dair baad dobara try karo"
    return s[:150]


def _clean_pkg(dest, mod):
    """tools/pylibs se sirf is package ki purani copy saaf karo."""
    for entry in os.listdir(dest):
        if entry == mod or entry.startswith(mod + "-"):
            p = os.path.join(dest, entry)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.remove(p)
                except OSError:
                    pass


def _install_wheel_blob(pkg, blob, _pg, pct_clean, pct_install):
    """Wheel verify (pehle!) -> purani copy saaf -> extract."""
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
        bad = z.testzip()
        if bad:
            raise Exception(f"corrupt file ({bad})")
        names = z.namelist()
    except zipfile.BadZipFile:
        raise Exception("corrupt download (zip nahi khula)")
    mod = pkg.replace("-", "_")
    if not any(n.startswith(mod + "/__init__.py") or n == mod + "/__init__.py" for n in names):
        if not any(".dist-info/METADATA" in n for n in names):
            raise Exception("wheel me package nahi mila")
    dest = pylibs_dir()
    _pg(f"{pkg}: purani copy saaf…", pct_clean)
    _clean_pkg(dest, mod)
    _pg(f"{pkg}: install…", pct_install)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        z.extractall(dest)


def _install_ytdlp_github(pypi_ver, _pg):
    """Fallback: PyPI se yt-dlp na utre to GitHub release tarball se.

    (github.com kuch networks par chalta hai jahan files.pythonhosted.org atak jata hai.)
    Tarball me yt-dlp/yt_dlp/ hota hai — sirf package nikalo + minimal dist-info likho.
    Returns report string.
    """
    import tarfile
    req = urllib.request.Request(
        "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
        headers={"User-Agent": "CreatorWatch", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        tag = json.load(r)["tag_name"]  # e.g. 2026.08.19 (PyPI: 2026.8.19)
    url = f"https://github.com/yt-dlp/yt-dlp/releases/download/{tag}/yt-dlp.tar.gz"
    blob = _download_blob(url, on_chunk=lambda got, total: _pg("yt-dlp: GitHub se download…", None))
    dest = pylibs_dir()
    _pg("yt-dlp: purani copy saaf…", None)
    _clean_pkg(dest, "yt_dlp")
    _pg("yt-dlp: install (GitHub)…", None)
    prefix = "yt-dlp/yt_dlp/"
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as t:
        members = [(m, m.name[len("yt-dlp/"):]) for m in t.getmembers()
                   if m.name.startswith(prefix)]
        members = [(m, rel) for m, rel in members
                   if rel.startswith("yt_dlp/") and ".." not in rel.split("/")]
        if not members:
            raise Exception("tarball me yt_dlp package nahi mila")
        byname = {m.name: m for m in t.getmembers()}
        for m, rel in members:
            src = byname[m.name]
            target = os.path.join(dest, rel)
            if src.isdir():
                os.makedirs(target, exist_ok=True)
            elif src.isfile():
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as f:
                    f.write(t.extractfile(src).read())
    # version detection (ext badge) ke liye minimal dist-info
    di = os.path.join(dest, f"yt_dlp-{pypi_ver}.dist-info")
    os.makedirs(di, exist_ok=True)
    with open(os.path.join(di, "METADATA"), "w") as f:
        f.write(f"Metadata-Version: 2.1\nName: yt-dlp\nVersion: {pypi_ver}\n")
    # sanity: import ho raha hai?
    try:
        import importlib
        importlib.invalidate_caches()
        m = importlib.import_module("yt_dlp.version")
        if not getattr(m, "__version__", ""):
            raise Exception("version nahi mili")
    except Exception as e:
        raise Exception(f"GitHub copy verify fail: {e}")
    return f"yt-dlp -> {pypi_ver} (GitHub)"


def latest_pypi_platform(pkg):
    """Platform-specific wheel (imageio-ffmpeg jese packages ke liye).
    Returns (ver, wheel_url) — is platform ka wheel."""
    import sys, platform
    req = urllib.request.Request(PYPI.format(pkg=pkg), headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    ver = data["info"]["version"]
    wheel_url = ""
    machine = platform.machine().lower()
    for u in data.get("urls", []):
        if u.get("packagetype") != "bdist_wheel":
            continue
        fn = u.get("filename", "").lower()
        if sys.platform == "win32":
            if "win_amd64" in fn or "win32" in fn:
                wheel_url = u["url"]
                break
        else:
            # linux: manylinux + arch match
            if "manylinux" in fn and (machine in fn or "x86_64" in fn):
                wheel_url = u["url"]
                break
    return ver, wheel_url


def _install_ffmpeg_blob(ver, blob, _pg):
    """imageio-ffmpeg wheel se ffmpeg binary nikal kar tools/ me rakho."""
    import sys
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
        bad = z.testzip()
        if bad:
            raise Exception(f"corrupt file ({bad})")
        names = z.namelist()
    except zipfile.BadZipFile:
        raise Exception("corrupt download (zip nahi khula)")
    # binary dhoondo: imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe
    cands = [n for n in names if "/binaries/ffmpeg-" in n and not n.endswith("/")]
    if not cands:
        raise Exception("wheel me ffmpeg binary nahi mili")
    # is platform ki binary chuno
    picked = ""
    for n in cands:
        nl = n.lower()
        if sys.platform == "win32" and "ffmpeg-win-" in nl:
            picked = n
            break
        elif sys.platform != "win32" and "ffmpeg-linux-" in nl:
            picked = n
            break
    if not picked:
        picked = cands[0]
    _pg("ffmpeg: install…", None)
    dest = _ffmpeg_tools_path()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        with z.open(picked) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
    if sys.platform != "win32":
        os.chmod(dest, 0o755)
    with open(_ffmpeg_version_file(), "w") as f:
        f.write(ver)
    # sanity: file mojood aur khaali nahi
    if not os.path.exists(dest) or os.path.getsize(dest) < 100000:
        raise Exception("ffmpeg binary verify fail")
    return f"ffmpeg -> {ver}"


def update_ffmpeg(progress=None):
    """ffmpeg ka latest binary imageio-ffmpeg wheel se -> tools/. Returns (ok, report)."""
    def _pg(title, pct=None):
        if progress:
            try:
                progress({"title": title, "pct": pct})
            except Exception:
                pass
    try:
        _pg("ffmpeg: latest version check…", None)
        ver, url = latest_pypi_platform(FFMPEG_PKG)
        if not url:
            return False, "ffmpeg: is platform ka wheel nahi mila"
        _pg("ffmpeg download…", None)
        blob = _download_blob(url, on_chunk=lambda got, total: _pg("ffmpeg download…", None))
        report = _install_ffmpeg_blob(ver, blob, _pg)
        return True, report
    except Exception as e:
        return False, f"ffmpeg FAIL: {_friendly_dl_error(e)}"


def update_engines(progress=None):
    """Dono engines + ffmpeg ke latest wheels PyPI se. Returns (ok, report)."""
    def _pg(title, pct=None):
        if progress:
            try:
                progress({"title": title, "pct": pct})
            except Exception:
                pass

    report, ok_all = [], True
    for i, pkg in enumerate(ENGINES):
        try:
            _pg(f"{pkg}: latest version check…", 5 + i * 35)
            ver, url = latest_pypi(pkg)
            if not url:
                report.append(f"{pkg}: wheel nahi mili")
                ok_all = False
                continue
            _pg(f"{pkg} download…", 10 + i * 35)
            base = 10 + i * 35
            try:
                blob = _download_blob(url, on_chunk=lambda got, total: _pg(f"{pkg} download…", base + int(20 * got / total)))
                _install_wheel_blob(pkg, blob, _pg, 30 + i * 35, 33 + i * 35)
                report.append(f"{pkg} -> {ver}")
            except Exception as dl_err:
                if pkg == "yt-dlp":
                    # PyPI atak/fail ho to GitHub release se (wo is network par chalta hai)
                    _pg("yt-dlp: PyPI se nahi utra — GitHub se try…", 15 + i * 35)
                    report.append(_install_ytdlp_github(ver, _pg))
                else:
                    raise
        except Exception as e:
            report.append(f"{pkg} FAIL: {_friendly_dl_error(e)}")
            ok_all = False
    # ffmpeg (binary) — alag se, taake user khud update kar sake
    _pg("ffmpeg: check…", 80)
    fok, frep = update_ffmpeg(progress=progress)
    report.append(frep)
    if not fok:
        ok_all = False
    return ok_all, "; ".join(report)


def clear_external():
    d = os.path.join(app_dir(), "tools", "pylibs")
    shutil.rmtree(d, ignore_errors=True)
    # ffmpeg (user-updated) bhi hatao — bundled wapas aayega
    for f in (_ffmpeg_tools_path(), _ffmpeg_version_file()):
        try:
            os.remove(f)
        except OSError:
            pass
