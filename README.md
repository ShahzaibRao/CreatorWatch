# 📥 CreatorWatch — v0.1.0

🌐 Language: **English** · [Roman Urdu](README.ur.md) · [Español](README.es.md) · [中文](README.zh.md)

Auto-track YouTube, TikTok, Instagram and X (Twitter) channels/profiles.
Add a link → a prospect folder is created → **only the latest video** downloads →
then only **new uploads** are downloaded on every interval.

---

## 1. Setup (first time)

```bash
cd downloader
python -m venv venv

# Windows:
venv\Scripts\activate
# Git-Bash / Linux / Mac:
source venv/bin/activate

pip install -r requirements.txt
python app.py
```

Then open: **http://127.0.0.1:5000**

> No need to install `ffmpeg` separately — it ships bundled via `imageio-ffmpeg`.

---

## 2. Adding a prospect (channel)

The **Add prospect** form on the dashboard:

| Field | Meaning |
|---|---|
| Name | Prospect name, e.g. `ali_tiktok` → folder `downloads/youtube_ali_tiktok/` is created |
| Channel / Profile link | YouTube channel, TikTok `@user`, Instagram profile, or X profile link |
| Every (min) | How often to check for new videos (5–1440, default 15) |
| Quality | `720p` (default) / `1080p` / `480p` / `360p` / `Best` — applies to YouTube |

**What happens on Add:**
1. Prospect folder is created under `downloads/`
2. **Only the single latest video** downloads in the background
3. All older videos are marked `skipped` — **they will never download**

---

## 3. Daily use

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

## 4. 🍪 Cookies Manager (`/cookies` page, header button)

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

## 5. Troubleshooting

| Error / Symptom | Cause + fix |
|---|---|
| `members-only / Join this channel` | Paid members-only video — test with a public channel |
| `Unable to extract data` (Instagram) | Login needed → import cookies (Instagram runs on the gallery-dl engine: yt-dlp marked it broken) |
| `login required` / `AuthRequired` / 0 items | Cookies missing/expired → re-import + Test (X needs logged-in `auth_token`) |
| Check page keeps spinning | Normal — a download is running (5–10 min on slow nets), watch the progress bar |
| `0 new` | No fresh upload, or everything is already in the DB |

---

## 6. Project structure

```
downloader/
├── app.py               # Flask dashboard + scheduler + thread pool
├── downloader.py        # yt-dlp/gallery-dl engine: fetch, download, first_run, auto-check
├── database.py          # SQLite: profiles, videos (done/skipped/seen), settings
├── translations.py      # UI strings: en / ur / es / zh (~90 keys)
├── data.db              # Database file (auto-created)
├── downloads/           # One folder per prospect: <platform>_<name>/
├── cookies.txt          # Your login cookies (managed from dashboard, never commit)
├── templates/           # dashboard.html, edit.html, cookies.html, settings.html
├── requirements.txt
└── server.log           # Server logs
```

**⚙ Performance (`/settings`):** parallel workers 1–10 (DB-persistent, live apply) + auto calculator (CPU/RAM/net → bottleneck suggestion).

**Constitution:** project memory lives in `constitution.md`.
