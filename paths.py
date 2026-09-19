"""User-data dir: exe folder when frozen (PyInstaller), else this folder."""
import os
import sys


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def ensure_pylibs():
    """EXE me engines alag se update hon: tools/pylibs sab se pehle sys.path me."""
    try:
        d = os.path.join(app_dir(), "tools", "pylibs")
        if os.path.isdir(d) and d not in sys.path:
            sys.path.insert(0, d)
    except Exception:
        pass
    return d if os.path.isdir(os.path.join(app_dir(), "tools", "pylibs")) else None

