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


def update_engines():
    """Dono engines ke latest wheels PyPI se -> tools/pylibs. Returns (ok, report)."""
    report, ok_all = [], True
    for pkg in ENGINES:
        try:
            ver, url = latest_pypi(pkg)
            if not url:
                report.append(f"{pkg}: wheel nahi mili")
                ok_all = False
                continue
            req = urllib.request.Request(url, headers={"User-Agent": "CreatorWatch"})
            with urllib.request.urlopen(req, timeout=600) as r:
                blob = r.read()
            dest = pylibs_dir()
            # purani copy saaf karo (sirf is package ki dirs)
            mod = pkg.replace("-", "_")
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
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                z.extractall(dest)
            report.append(f"{pkg} -> {ver}")
        except Exception as e:
            report.append(f"{pkg} FAIL: {str(e)[:150]}")
            ok_all = False
    return ok_all, "; ".join(report)


def clear_external():
    d = os.path.join(app_dir(), "tools", "pylibs")
    shutil.rmtree(d, ignore_errors=True)
