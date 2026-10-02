# 📥 CreatorWatch

🌐 Language: **English** · [Roman Urdu](README.ur.md) · [Español](README.es.md) · [中文](README.zh.md)

Auto-track YouTube, TikTok, Instagram and X (Twitter) channels/profiles.
Add a link → a prospect folder is created → **only the latest video** downloads →
then only **new uploads** are downloaded on every interval.

## Two parts

| Part | What it does | Where it runs |
|---|---|---|
| **Desktop app** | Dashboard, scheduler, downloads, local SQLite DB | Your PC (Windows EXE / Linux / Python source) |
| **License server** | Accounts, license keys, web UI, admin panel | Cloud — `cw.raoshahzaib.site` (see `license-server/`) |

The desktop app stays 100% local — downloads, database and scheduler never
leave your machine. The cloud part only handles accounts + licenses.

---

## Install / Run — Desktop app

### Option A — Windows installer (easy)
Download `CreatorWatch-Setup-X.Y.Z.exe` from
[Releases](https://github.com/ShahzaibRao/CreatorWatch/releases) → install →
double-click the desktop icon. No Python needed.

- Closing the window (X) keeps it running in the **system tray** (right-click → Open / Exit).
- Opening it again while it's running brings back the same window (single instance).
- Updates from inside the app (⬆ Updates page).

### Option B — Python source

```bash
git clone https://github.com/ShahzaibRao/CreatorWatch
cd CreatorWatch
python -m venv venv

# Windows:
venv\Scripts\activate
# Linux / Mac:
source venv/bin/activate

pip install -r requirements.txt
python app.py            # browser mode → http://127.0.0.1:5000
python app.py --app      # desktop window mode
```

> No need to install `ffmpeg` separately — it ships bundled via `imageio-ffmpeg`.

### Option C — Linux
`installer/install.sh [path]` (default `~/.local/share/creatorwatch`) →
`creatorwatch` command + app menu entry. Needs python3-venv; for the desktop
window also webkit (`python3-gi gir1.2-webkit2-4.1`), else browser mode.

**User data location:** `%APPDATA%\CreatorWatch` on Windows
(`~/.config/creatorwatch` on Linux) — database, cookies and logs live there,
safe across uninstall/reinstall. Downloads default to `~/Downloads/CreatorWatch`.

---

## License server — run it

The server behind `cw.raoshahzaib.site`: landing page, signup/login,
user dashboard (licenses), admin panel (users, revenue, devices).

```bash
cd license-server
```

| Method | Command |
|---|---|
| Python | `pip install -r requirements.txt && python app.py` → http://127.0.0.1:5001 |
| Docker | `docker build -t creatorwatch-license .` then `docker run -d -p 5001:5001 -e LICENSE_ADMIN_TOKEN=xxx -v licdata:/data creatorwatch-license` |
| Docker Compose | `docker compose up -d` (set the 3 secrets first — see `license-server/README.md`) |

Admin panel: `http://127.0.0.1:5001/admin` (token = `LICENSE_ADMIN_TOKEN`).
Full docs: [`license-server/README.md`](license-server/README.md).

---

## What's in the `cloud` branch

- **License-key SaaS:** Flask license server (M1) + desktop license gate (M2) —
  key validation, per-machine seats, offline grace.
- **Web UI (M3a):** landing, signup/login, user dashboard, **admin panel**
  (users, revenue, active devices; create/edit/revoke/delete licenses;
  deactivate devices; user key reveal + copy).
- **Desktop polish:** custom app icon, system tray (X → background), single
  instance, icon-as-logo + favicon, header alignment fixes.
- **Download-complete OS notifications** (Windows toast with click-to-open).
- **YouTube POT auto-heal** (local Deno PO-token server).

---

## 1. Adding a prospect (channel)

The **Add prospect** form on the dashboard:

| Field | Meaning |
|---|---|
| Name | Prospect name, e.g. `ali_tiktok` → folder `downloads/youtube/ali_tiktok/` |
| Channel / Profile link | YouTube channel, TikTok `@user`, Instagram profile, or X profile link |
| Every (min) | How often to check for new videos (5–1440, default 15) |
| Quality | `720p` (default) / `1080p` / `480p` / `360p` / `Best` — applies to YouTube |

**What happens on Add:**
1. Prospect folder is created under `downloads/`
2. **Only the single latest video** downloads in the background
3. All older videos are marked `skipped` — **they will never download**

---

## 2. Daily use

| Button | Action |
|---|---|
| **Check** | Check right now + download new uploads in background (watch the live progress bar) |
| **Check all now** | Check all active prospects at once (max parallel workers) |
| **⏸ Stop / ▶ Resume** | Pause / resume auto-check (missed videos are caught on next check) |
| **Edit** | Change name, link, interval, quality (folder stays the same) |
| **Del** | Delete prospect + its download history |

**Status pills:** `OK` = fine · `Error` (hover for reason) · `Working` = first download running · `Paused` = stopped.

**Good to know:**
- Every profile checks itself on its own interval (scheduler submits due profiles every 1 min).
- Downloads are recorded in the **database** — even if you delete a file from its folder, it **won't download again**.
- `0 new — no fresh upload` means the creator hasn't posted anything new.

**Extras:** 🔔 bell with count badge for new downloads (+ per-item NEW pills), live progress bars, ⚙ workers indicator, 🌐 language switcher (EN/UR/ES/中文), ◐ light/dark theme.

---

## 3. 🍪 Cookies Manager (`/cookies` page, header button)

Instagram and X (Twitter) **don't serve profile data without login**.
YouTube + TikTok usually work without cookies.

**How to import:**
1. Install the **"Get cookies.txt LOCALLY"** browser extension
2. Log in on that site (e.g. instagram.com)
3. Export via the extension → copy the text
4. Paste on the `/cookies` page and press **Save** (format is auto-checked)

**The page shows:**
- **Status:** file active/missing, format OK, usable/expired cookie counts, sites, size/date
- **Per-site cards:** Instagram / X / YouTube / TikTok — ✅ Ready · ❌ Login missing · ⚠️ Expired · ○ Optional
- **Live check:** "Test Now" does a real site fetch (10–30 sec) — **Valid / Invalid** per platform. Invalid → import again
- **Delete:** remove cookies in one click

Cookies apply to the very next check — no restart needed.

---

## 4. Troubleshooting

| Error / Symptom | Cause + fix |
|---|---|
| `members-only / Join this channel` | Paid members-only video — test with a public channel |
| `Unable to extract data` (Instagram) | Login needed → import cookies (Instagram runs on the gallery-dl engine: yt-dlp marked it broken) |
| `login required` / `AuthRequired` / 0 items | Cookies missing/expired → re-import + Test (X needs logged-in `auth_token`) |
| Check page keeps spinning | Normal — a download is running (5–10 min on slow nets), watch the progress bar |
| `0 new` | No fresh upload, or everything is already in the DB |

---

## 5. Project structure

```
CreatorWatch/
├── app.py               # Flask dashboard + scheduler + thread pool + tray + singleton
├── downloader.py        # yt-dlp/gallery-dl engine: fetch, download, first_run, auto-check
├── database.py          # SQLite: profiles, videos (done/skipped/seen), settings
├── license_client.py    # M2: license gate (validates against license server)
├── paths.py             # app_dir() vs user_data_dir() (%APPDATA%/CreatorWatch)
├── translations.py      # UI strings: en / ur / es / zh
├── templates/           # dashboard, edit, cookies, settings, updates, logs, activate
├── assets/              # icon.ico / icon.png
├── tools/               # deno, potserver, ffmpeg/ffprobe, yt-dlp
├── installer/           # Inno Setup script (Windows) + install.sh (Linux)
├── .github/workflows/   # release.yml — builds EXE + installer + Linux tarball
├── requirements.txt
└── license-server/      # M1+M3a: accounts API, web UI, admin panel
    ├── app.py
    ├── templates/
    ├── Dockerfile
    ├── docker-compose.yml
    └── README.md
```

**⚙ Performance (`/settings`):** parallel workers 1–10 (DB-persistent, live apply) + auto calculator (CPU/RAM/net → bottleneck suggestion).

**Constitution:** project memory lives in `constitution.md`.
