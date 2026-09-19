# 📥 Prospect Downloader

YouTube, TikTok, Instagram aur X (Twitter) ke channels/profiles ko auto-track karo.
Link add karo → prospect folder banta hai → **sirf latest video** download hoti hai →
uske baad har interval par **sirf nayi uploads** download hoti hain.

---

## 1. Setup (pehli bar)

```bash
cd downloader
python -m venv venv

# Windows:
venv\Scripts\activate
# Git-Bash / Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
python app.py
```

Phir browser me kholo: **http://127.0.0.1:5000**

> `ffmpeg` alag se install karne ki zaroorat nahi — `imageio-ffmpeg` ke sath bundled aata hai.

---

## 2. Prospect (channel) add karna

Dashboard pe **Add prospect** form:

| Field | Matlab |
|---|---|
| Name | Prospect ka naam, e.g. `ali_tiktok` → folder `downloads/youtube_ali_tiktok/` banega |
| Channel / Profile link | YouTube channel, TikTok `@user`, Instagram profile, ya X profile ka link |
| Every (min) | Kitne minute baad nayi video check ho (5–1440, default 15) |
| Quality | `720p` (default) / `1080p` / `480p` / `360p` / `Best` — sirf YouTube par lagti hai |

**Add dabate hi kya hota hai:**
1. Prospect folder `downloads/` me ban jata hai
2. Background me **sirf sab se latest 1 video** download hoti hai
3. Baqi purani videos `skipped` mark ho jati hain — **wo kabhi download nahi hongi**

---

## 3. Roz ka istemal

| Button | Kaam |
|---|---|
| **Check** | Usi waqt check + nayi upload download (2–10 min lag sakta hai, page wait karega) |
| **Check all now** | Sab active prospects ek sath check |
| **⏸ Stop / ▶ Resume** | Auto-check rokna / dobara chalana (missed videos agle check me pakdi jayengi) |
| **Edit** | Naam, link, interval, quality badlo (folder wahi rehta hai) |
| **Del** | Prospect + uska download record delete |

**Status pills:** `OK` = sab theek · `Error` (hover karo to wajah) · `Working` = pehli download chal rahi · `Paused` = ruka hua.

**Yaad rakho:**
- Har profile apne interval par **khud check hoti hai** (scheduler har 1 min me due profiles dekhta hai).
- Download ki hui video ka record **database me rehta hai** — folder se file delete bhi kar do to **dobara download nahi hogi**.
- `0 new — koi fresh upload nahi` ka matlab: creator ne kuch naya dala hi nahi.

---

## 4. 🍪 Cookies Manager (`/cookies` page, header me button)

Instagram aur X (Twitter) **bina login ke profile data nahi dete**.
YouTube + TikTok aam tor par baghair cookies chalte hain.

**Import karne ka tariqa:**
1. Browser me **"Get cookies.txt LOCALLY"** extension lagao
2. Us site pe login karo (e.g. instagram.com)
3. Extension se **Export** → text copy karo
4. `/cookies` page pe paste karke **Save** dabao (format auto-check hota hai)

**Page pe kya hai:**
- **Status:** file active/missing, format OK, usable/expired cookies count, sites, size/date
- **Live check:** "Abhi Test Karo" — asli site fetch karke **Valid / Invalid** batata hai (10–30 sec). Invalid aaye to cookies dobara import karo
- **Delete:** ek click pe cookies hatao

Save karte hi agli har check me cookies khud use hongi — restart zaroori nahi.

---

## 5. Masail (troubleshooting)

| Error / Nishani | Wajah + Hal |
|---|---|
| `members-only / Join this channel` | Video paid members ke liye hai — public channel se test karo |
| `Unable to extract data` (Instagram) | Login chahiye → cookies import karo |
| `login required` / profile se `0` items | Cookies missing/expire → dobara import + Test karo |
| `Requested format is not available` | Purana version tha — naye code me platform-wise format + bundled ffmpeg hai |
| Check dabane par page der tak ghoomta hai | Normal hai — download ho rahi hai (slow net par 5–10 min) |
| `0 new` | Koi fresh upload nahi, ya sab pehle se DB me hain |

---

## 6. Project structure

```
downloader/
├── app.py               # Flask dashboard + scheduler (har 1 min due-check)
├── downloader.py        # yt-dlp engine: fetch, download, first_run, auto-check
├── database.py          # SQLite: profiles, videos (done/skipped), metrics
├── data.db              # Database file (auto-banti hai)
├── downloads/           # Har prospect ka folder: <platform>_<name>/
├── cookies.txt          # Tumhari login cookies (dashboard se manage hoti hain)
├── templates/
│   ├── dashboard.html   # Main UI (light/dark toggle, responsive)
│   ├── edit.html        # Prospect edit form
│   └── cookies.html     # Cookies manager
├── requirements.txt
└── server.log           # Server logs
```

**Theme:** top-right button se Light/Dark — choice browser me save rehti hai. Mobile + desktop dono par responsive hai.
