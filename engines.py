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
PYPI = "https://pypi.org/pypi/{pkg}/json"
UA = {"User-Agent": "CreatorWatch", "Accept": "application/json"}


def pylibs_dir():
    d = os.path.join(app_dir(), "tools", "pylibs")
    os.makedirs(d, exist_ok=True)
    return d


def active_versions():
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


def _download_blob(url, on_chunk=None, timeout=600, tries=3):
    """Wheel download with retry — DNS/network blips par foran haar nahi manta."""
    import time
    last_err = None
    for attempt in range(1, tries + 1):
        try:
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
                    if total and on_chunk:
                        on_chunk(got, total)
            blob = b"".join(chunks)
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


def update_engines(progress=None):
    """Dono engines ke latest wheels PyPI se -> tools/pylibs. Returns (ok, report)."""
    def _pg(title, pct=None):
        if progress:
            try:
                progress({"title": title, "pct": pct})
            except Exception:
                pass

    report, ok_all = [], True
    for i, pkg in enumerate(ENGINES):
        try:
            _pg(f"{pkg}: latest version check…", 5 + i * 45)
            ver, url = latest_pypi(pkg)
            if not url:
                report.append(f"{pkg}: wheel nahi mili")
                ok_all = False
                continue
            _pg(f"{pkg} download…", 12 + i * 45)
            base = 12 + i * 45
            blob = _download_blob(url, on_chunk=lambda got, total: _pg(f"{pkg} download…", base + int(25 * got / total)))
            # Wheel VERIFY karo PEHLE — purani working copy tabhi delete hogi jab
            # nayi poori utri ho (adhoori download se engine toot jata tha).
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
                # kuch wheels me top-level dir alag hoti hai — kam az kam dist-info check karo
                if not any(".dist-info/METADATA" in n for n in names):
                    raise Exception("wheel me package nahi mila")
            dest = pylibs_dir()
            # purani copy saaf karo (sirf is package ki dirs)
            _pg(f"{pkg}: purani copy saaf…", 38 + i * 45)
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
            _pg(f"{pkg}: install…", 42 + i * 45)
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                z.extractall(dest)
            report.append(f"{pkg} -> {ver}")
        except Exception as e:
            report.append(f"{pkg} FAIL: {_friendly_dl_error(e)}")
            ok_all = False
    return ok_all, "; ".join(report)


def clear_external():
    d = os.path.join(app_dir(), "tools", "pylibs")
    shutil.rmtree(d, ignore_errors=True)
