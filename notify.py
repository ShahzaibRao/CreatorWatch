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


def _windows_toast(title, lines, folder):
    # Har bar NAYA toaster — singleton alag threads par COM issue deta hai
    # (test Flask thread par kaam karta, download daemon thread par fail).
    from windows_toasts import WindowsToaster, Toast
    toaster = WindowsToaster(_APP)
    t = Toast()
    t.text_fields = [title] + lines[:2]
    if folder:
        t.on_activated = lambda _: open_folder(folder)
    toaster.show_toast(t)


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


# ---- Batched notifications ----
# Kai prospects ek sath download karein to 20+ toasts Windows suppress kar deta hai.
# Is liye queue me jama karo, har 20 sec me EK summary toast bhejo.
_BATCH = []  # [(profile_name, count, folder), ...]
_BATCH_LOCK = threading.Lock()
_BATCH_THREAD_STARTED = False

def download_complete_batched(profile_name, count, folder=""):
    """Queue me daalo — background thread har 20 sec me summary bhejega."""
    global _BATCH_THREAD_STARTED
    if not count:
        return
    with _BATCH_LOCK:
        _BATCH.append((profile_name, count, folder or ""))
        if not _BATCH_THREAD_STARTED:
            _BATCH_THREAD_STARTED = True
            threading.Thread(target=_batch_worker, daemon=True, name="toast-batch").start()

def _batch_worker():
    """Har 20 sec: queue khaali karo, ek summary toast bhejo."""
    import time
    while True:
        time.sleep(20)
        with _BATCH_LOCK:
            items = _BATCH[:]
            _BATCH.clear()
        if not items:
            continue
        try:
            total = sum(c for _, c, _ in items)
            if len(items) == 1:
                # Sirf ek prospect — purana style
                name, count, folder = items[0]
                _notify(name, count, folder)
            else:
                # Kai prospects — summary
                names = ", ".join(n for n, _, _ in items[:3])
                if len(items) > 3:
                    names += f" +{len(items)-3} aur"
                title = f"\U0001F4E5 {len(items)} prospects se {total} nayi videos"
                lines = [names, "Click karo (pehle wale ka folder khulega)"]
                # Pehle wale ka folder (click par)
                first_folder = items[0][2]
                if platform.system() == "Windows":
                    _windows_toast(title, lines, first_folder)
                else:
                    _linux_toast(title, lines)
        except Exception as e:
            print(f"[TOAST BATCH FAIL] {e}", flush=True)
