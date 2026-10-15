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
    print(f"[TOAST-DEBUG] _windows_toast start: title={title[:30]}", flush=True)
    try:
        from windows_toasts import WindowsToaster, Toast
        print(f"[TOAST-DEBUG] imports OK", flush=True)
        toaster = WindowsToaster(_APP)
        print(f"[TOAST-DEBUG] toaster created", flush=True)
        t = Toast()
        t.text_fields = [title] + lines[:2]
        if folder:
            t.on_activated = lambda _: open_folder(folder)
        print(f"[TOAST-DEBUG] calling show_toast...", flush=True)
        toaster.show_toast(t)
        print(f"[TOAST-DEBUG] show_toast returned OK", flush=True)
    except Exception as e:
        import traceback
        print(f"[TOAST-DEBUG] FAIL: {type(e).__name__}: {e}", flush=True)
        print(traceback.format_exc()[:800], flush=True)
        raise


def _linux_toast(title, lines):
    if not shutil.which("notify-send"):
        return
    subprocess.Popen(
        ["notify-send", "--app-name", _APP, "--icon", "folder-download",
         title, "\n".join(lines)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _notify(profile_name, count, folder):
    print(f"[TOAST-DEBUG] _notify: {profile_name} count={count}", flush=True)
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
        print(f"[TOAST-DEBUG] _notify done OK", flush=True)
    except Exception as e:
        print(f"[TOAST FAIL] {e}", flush=True)


def download_complete(profile_name, count, folder=""):
    """Fire-and-forget: runs in a daemon thread, never blocks the worker."""
    if not count:
        return
    threading.Thread(target=_notify, args=(profile_name, count, folder or ""),
                     daemon=True, name="toast").start()


# ---- Toast serialization ----
# Kai threads ek sath toast bhejein to Windows COM/WinRT garbar karta hai.
# Lock se ek waqt me sirf ek toast — baqi queue me wait karte hain.
_TOAST_LOCK = threading.Lock()

def download_complete_batched(profile_name, count, folder=""):
    """Serialized toast — ek waqt me ek hi (Windows WinRT thread-safe nahi)."""
    print(f"[TOAST-DEBUG] download_complete_batched: {profile_name} count={count}", flush=True)
    if not count:
        print(f"[TOAST-DEBUG] count=0, skip", flush=True)
        return
    def _serialized():
        print(f"[TOAST-DEBUG] thread started for {profile_name}", flush=True)
        with _TOAST_LOCK:
            print(f"[TOAST-DEBUG] lock acquired for {profile_name}", flush=True)
            _notify(profile_name, count, folder or "")
    threading.Thread(target=_serialized, daemon=True, name="toast").start()
    print(f"[TOAST-DEBUG] thread spawned for {profile_name}", flush=True)
