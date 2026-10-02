"""User-data dir: exe folder when frozen (PyInstaller), else this folder."""
import os
import sys


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def is_frozen():
    return bool(getattr(sys, "frozen", False))


_migrated = False

def user_data_dir():
    """User ka PERMANENT data (data.db, cookies.txt, server.log).
    Program {app} me rehta hai, lekin ye data uninstall/reinstall se MEHFOOZ jagah:
    Windows: %APPDATA%\\CreatorWatch | Linux: ~/.config/creatorwatch
    Pehli dafa purane app_dir() wali files khud-ba-khud yahan move ho jati hain."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "CreatorWatch")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        d = os.path.join(base, "creatorwatch")
    os.makedirs(d, exist_ok=True)
    _migrate_user_files(d)
    return d


def _migrate_user_files(d):
    """Purani location (install folder / repo folder) se data.db, cookies.txt,
    server.log nayi permanent jagah lao — sirf jab wahan pehle se na hon."""
    global _migrated
    if _migrated:
        return
    _migrated = True
    old = app_dir()
    if os.path.abspath(old) == os.path.abspath(d):
        return
    for name in ("data.db", "cookies.txt", "server.log"):
        src, dst = os.path.join(old, name), os.path.join(d, name)
        try:
            if os.path.exists(src) and not os.path.exists(dst):
                os.replace(src, dst)
                print(f"[DATA] {name}: {old} -> {d}", flush=True)
        except Exception as e:
            print(f"[DATA] {name} migrate fail: {e}", flush=True)


def ensure_pylibs():
    """EXE me engines alag se update hon: tools/pylibs sab se pehle sys.path me."""
    try:
        d = os.path.join(app_dir(), "tools", "pylibs")
        if os.path.isdir(d) and d not in sys.path:
            sys.path.insert(0, d)
    except Exception:
        pass
    return d if os.path.isdir(os.path.join(app_dir(), "tools", "pylibs")) else None

