# Constitution — CreatorWatch (project memory)

> Ye file is project ki yaad-dasht hai: **kya banaya, kaise banaya, har file kya karti hai,
> kaun se features ban chuke, aur progress kahan tak hai.** Naya kaam shuru karne se pehle
> ise parh lo taake purane faisle dobara na bhoolo.

---

## 1. Kya banaya

**CreatorWatch** — ek local web-app jo YouTube, TikTok, Instagram aur X (Twitter)
ke channels/profiles ko track karti hai:

- User channel/profile link add karta hai → `downloads/<platform>_<name>/` folder banta hai
- Add hote hi **sirf sab se latest 1 video** background me download hoti hai,
  baqi purani videos `skipped` mark (kabhi download nahi hongi)
- Uske baad har profile **apne interval** (default 15 min) par khud check hoti hai —
  **sirf bilkul nayi uploads** download hoti hain (e.g. 12 ghante baad nayi video aaye to wahi ek)
- Download ka record **SQLite DB** me rehta hai — folder se file delete bhi kar do to
  **dobara download nahi hoti**
- Dashboard par metrics: total prospects, total videos, storage, per-profile counts,
  recent downloads, status pills (OK / Error / Working / Paused)

**Stack:** Python + Flask + APScheduler + yt-dlp + SQLite + bundled ffmpeg (`imageio-ffmpeg`).
Server: `http://127.0.0.1:5000` (Flask dev server, local use ke liye).

---

## 2. Kaise banaya (architecture faisle)

1. **yt-dlp engine** — sare platforms ek hi library se (koi scraper/API key nahi).
   Flat `extract_info` se fast listing (download nahi), phir sirf nayi IDs download.
2. **DB = source of truth** — `videos(profile_id, video_id)` UNIQUE. File-system nahi,
   DB faisla karti hai dobara download hogi ya nahi (`done` + `skipped` dono block karte hain).
3. **Scheduler** — APScheduler har 1 min me `get_due_profiles()` chalata hai
   (`last_check + interval_minutes` guzar gaya ho to check). Manual `/check` bhi hai.
4. **Blocking downloads** — `/check` request download khatam hone tak wait karta hai
   (slow net par 5–10 min). Is liye `/add` par first-download **background thread** me hai.
5. **ffmpeg bundled** — `imageio-ffmpeg` se merge formats chalte hain, alag install nahi chahiye.
6. **Login via cookies.txt** — Insta/X bina login profile data nahi dete, is liye
   dashboard se import/test/delete wala Cookies Manager hai.

---

## 3. File-by-file memory

| File | Kaam |
|---|---|
| `app.py` | Flask app + scheduler. Routes: `/` dashboard, `/add` (background first-download), `/edit`, `/delete`, `/check/<id>`, `/check_all`, `/pause`, `/resume`, `/cookies` (GET/POST import + `?test=1` live check), `/cookies/delete`, `/api/metrics`. Helpers: `COOKIES_PATH`, `cookies_info()` (format/expiry health), `live_cookie_test()` (asli fetch), `TEST_URLS`, `run_first_download()` |
| `downloader.py` | `detect_platform()` (youtube/tiktok/instagram/twitter incl. x.com), `normalize_profile_url()` (x.com→twitter.com, YT channel→`/videos`), `prospect_folder()`, `_ydl_opts_flat()`, `fetch_latest_entries()` (YT channel tabs → videos+shorts tabs, newest-first, max 10), `QUALITY_FORMATS` + `_ffmpeg()` + `_env_with_ffmpeg()` (subprocess ffmpeg PATH), `_gdl()` helper, `ig_fetch()` + `ig_download()` (gallery-dl Instagram engine — yt-dlp insta broken hai), `download_one(url, folder, quality, platform)` (IG→gallery-dl, TT/X→`best`, YT→quality map), `LOGIN_HINT` + `_friendly_error()`, `first_run()` (latest 1 download + baqi `mark_seen`), `check_profile()`, `check_all_profiles()`, `check_due_profiles()` |
| `database.py` | `profiles(id,name,platform,url,folder,created_at,last_check,status,interval_minutes,last_error,quality)` + auto-migration. `videos(...,status done/skipped)` + UNIQUE. Functions: `add_profile`, `update_profile`, `_platform`, `get_profiles/profile`, `update_last_check`, `set_profile_error`, `get_due_profiles`, `delete_profile`, `add_video`, `video_exists` (done+skipped dono True), `mark_seen`, `set_status`, `get_recent_videos` (done only), `get_metrics` (done counts + storage walk) |
| `templates/dashboard.html` | Premium UI: light/dark toggle (localStorage), SVG icons, stat cards, add form (interval+quality), prospects table (badges, pills, Check/Stop-Resume/Edit/Del), recent list, cookies notice. Responsive (desktop/tablet/mobile) |
| `templates/edit.html` | Prospect edit form (name/url/interval/quality, folder same rehta hai) |
| `templates/cookies.html` | Cookies Manager: status card, live test (`?test=1`), import textarea, delete |
| `requirements.txt` | `yt-dlp`, `Flask`, `APScheduler`, `imageio-ffmpeg`, `gallery-dl` (Instagram engine) |
| `README.md` | User guide (Urdu): setup, istemal, cookies, troubleshooting |
| `data.db` | SQLite file (auto-banti hai, `init_db` + migrations) |
| `downloads/` | Prospect folders: `<platform>_<sanitized_name>/` |
| `cookies.txt` | Optional login cookies (dashboard se manage). Git me kabhi commit NA karo |
| `server.log` | Server + download progress logs |
| `venv/` | Virtual env (repo me track nahi hota) |

---

## 4. Features (ban chuke — tareekh ke hisab se)

1. ✅ Core prototype: DB + yt-dlp engine + Flask dashboard + metrics
2. ✅ venv setup + local run (`server.log`, HTTP 200 verified)
3. ✅ YouTube channel-tabs bug fix (root link tabs deta tha → `/videos` normalize + tab recursion)
4. ✅ Per-profile interval auto-check + first-time instant download + no re-download guarantee
5. ✅ ffmpeg fix (bundled) + Edit page + quality options (720p/1080p/480p/360p/best)
6. ✅ Premium redesign: light/dark toggle, SVG icons, responsive mobile+web
7. ✅ Latest-only policy: `first_run()` (nayi = sirf future uploads) + Stop/Resume (pause)
8. ✅ TikTok format fix (platform-aware `best`) + Twitter/X support + x.com normalize + login hints
9. ✅ Cookies Manager: dashboard import/delete + format check + live validity test
10. ✅ README (user guide) + ye constitution file
11. ✅ Instagram engine gallery-dl par shift (yt-dlp ne officially broken mark kiya hai) + end-to-end verified
12. ✅ X/Twitter bhi gallery-dl par (is yt-dlp me x.com support nahi; tweet_id field; text-only posts skip-mark) + end-to-end verified (10 files) + progress bars (live %, /api/jobs polling) + notification bell (unseen videos, /api/notifications, mark-read)
13. ✅ Multi-threading: ThreadPoolExecutor (pool 10, dynamic gate), per-profile sequential, busy-skip (RUNNING set), scheduler submit_due, /check background, workers indicator, threaded Flask
14. ✅ Workers setting: DB-persistent `max_workers` (1–10), `/settings` page with slow-vs-fast guidance, live apply no-restart, header indicator links to settings
15. ✅ Workers calculator: CPU cores/RAM/Net inputs → bottleneck formula (cpu=cores-1, ram=40%÷450MB, net=÷10Mbps, min of three) + one-click Apply + ready chart (cores detect via os.cpu_count)
16. ✅ Multi-language (EN/UR/ES/中文): translations.py (~90 keys), lang cookie + /lang route, header dropdown on all pages, default Roman Urdu
17. ✅ v0.1.0 production release → https://github.com/ShahzaibRao/CreatorWatch.git (main + tag v0.1.0, .gitignore, footer version)
18. ✅ Multi-language READMEs: README.md (EN) + README.ur/es/zh.md with nav bar (main branch, post-v0.1.0)
19. ✅ EXE + auto-update: paths.py (frozen user-data dir), PyInstaller onefile (54MB, templates+gallery-dl+ffmpeg bundled), gallery-dl in-process when frozen, EXE auto-opens browser, /updates page (GitHub release check, .exe download+restart updater, engine pip upgrade in source mode), 2-way install docs (source vs Releases EXE)
20. ✅ Desktop app: pywebview window (same UI, no browser needed, --app flag for source, browser fallback), engines.py (PyPI wheels -> tools/pylibs, external/bundled switch, restart), Inno Setup script (installer/CreatorWatch.iss, shortcuts, launch-after-install), 💻 Download button (release tag link) in webapp header
21. ✅ Real installer (SaaS-ready desktop): Inno 6.7 installed+compiled → installer/CreatorWatch-Setup-0.1.0.exe (58MB), silent-install tested (shortcuts+uninstaller+data.db in install dir), desktop window polls APIs (GUI verified via logs), "Install Required Packages" first-run state verified

---

## 5. Maloom limits (dobara debug na karna)

- **Instagram/X profile listing bina valid cookies ke fail/empty** — yt-dlp ki limit hai, bug nahi.
- **Members-only / paid videos** download nahi hongi (join-gated content).
- **`/check` blocking hai** — slow net par minutes lagte hain, ye normal hai.
- **Windows console me emoji print** `UnicodeEncodeError` de sakta hai — code me Urdu text se bacho ya utf-8 wrap karo.
- **Concurrent Flask dev servers** — ek se zyada `app.py` chal jaye to purana code serve hota hai; `taskkill /F /FI "IMAGENAME eq python*"` se saaf karo (fbash me `pkill` nahi hai).
- **Jinja template cache** — HTML badalne ke baad server restart zaroori hai.
- **`/check` ab background me hai** — foran redirect + progress bar (JS har 3 sec `/api/jobs` poll). Purana blocking result-page hata diya.
- **Bell** purani videos ke liye clean start karti hai (`seen` default 1, nayi downloads `seen=0`).
- **X/Twitter ke liye logged-in x.com cookies (auth_token) lazmi** — warna gallery-dl AuthRequired deta hai.
- **`cookies.txt`, `data.db`, `downloads/`, `venv/`, `server.log`** personal/runtime files hain — share/commit mat karo.

## 6. Agle possible kaam (pending ideas)

- [ ] Non-blocking check (job queue + progress bar)
- [ ] Per-video quality/size dashboard me dikhana
- [ ] Telegram/Email alert jab nayi video download ho
- [ ] Production server (waitress/gunicorn) + login password
- [ ] Purane prospects ko "latest-only" par migrate karne ka one-click button
