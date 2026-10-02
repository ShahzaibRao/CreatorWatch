"""OS-level download-complete notifications (cloud branch).

When a check/first-download finishes with new files, show a native popup.
Clicking it opens the creator's folder.

- Windows: `windows-toasts` (optional; win32-only dep in requirements.txt).
- Linux: `notify-send` if present (body only — click actions need a
  notification-daemon listener, so best-effort, no click).
- Anything else, or import failure: silent no-op. The in-app bell (top)
  still works everywhere, so nothing is lost.

NOTE for exe builds: if the toast never appears in the PyInstaller exe,
add `--collect-all windows_toasts --collect-all winrt` to
.github/workflows/release.yml (winrt's submodules are often missed).
"""

import os
import platform
import shutil
import subprocess
import threading

_APP = "CreatorWatch"


def open_folder(path):
    """Open a folder in the OS file manager. Best-effort, never raises."""
    if not path:
        return
    try:
        sysname = platform.system()
        if sysname == "Windows":
            os.startfile(path)
        elif sysname == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


_toaster = None  # lazy singleton: one WindowsToaster per process


def _windows_toast(title, lines, folder):
    global _toaster
    from windows_toasts import WindowsToaster, Toast
    if _toaster is None:
        _toaster = WindowsToaster(_APP)
    t = Toast()
    t.text_fields = [title] + lines[:2]
    if folder:
        t.on_activated = lambda _: open_folder(folder)
    _toaster.show_toast(t)


def _linux_toast(title, lines):
    if not shutil.which("notify-send"):
        return
    subprocess.Popen(
        ["notify-send", "--app-name", _APP, "--icon", "folder-download",
         title, "\n".join(lines)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _notify(profile_name, count, folder):
    noun = "video" if count == 1 else "videos"
    title = f"\U0001F4E5 {profile_name}"
    if folder and platform.system() == "Windows":
        hint = "Click karo folder kholne ke liye"
    elif folder:
        hint = f"Folder: {folder}"
    else:
        hint = ""
    lines = [f"{count} nayi {noun} download ho gayi"]
    if hint:
        lines.append(hint)
    try:
        if platform.system() == "Windows":
            _windows_toast(title, lines, folder)
        else:
            _linux_toast(title, lines)
    except Exception as e:
        print(f"[TOAST FAIL] {e}", flush=True)


def download_complete(profile_name, count, folder=""):
    """Fire-and-forget: runs in a daemon thread, never blocks the worker."""
    if not count:
        return
    threading.Thread(target=_notify, args=(profile_name, count, folder or ""),
                     daemon=True, name="toast").start()
