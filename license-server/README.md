# CreatorWatch License Server — M1 + M3a

Tiny cloud service for accounts + license keys, with a public website
(landing, signup/login, dashboard) and an admin panel. The desktop app
stays 100% local; on startup it calls `POST /api/licenses/validate`
(M2: login gate in the app).

## Dev run

```bash
cd license-server
pip install -r requirements.txt
python app.py        # http://127.0.0.1:5001
```

## Run with Docker

```bash
cd license-server
docker build -t creatorwatch-license .
docker run -d --name creatorwatch-license -p 5001:5001 \
  -e LICENSE_ADMIN_TOKEN="tumhara-strong-token" \
  -e LICENSE_SESSION_SECRET="tumhara-random-secret" \
  -e LICENSE_KEY_SECRET="tumhara-ek-aur-random-secret" \
  -v licdata:/data \
  creatorwatch-license
# open http://127.0.0.1:5001
```

## Run with Docker Compose

```bash
cd license-server
# production: teenon secrets set karo (warna defaults = sirf local test ke liye)
export LICENSE_ADMIN_TOKEN="tumhara-strong-token"
export LICENSE_SESSION_SECRET="tumhara-random-secret"
export LICENSE_KEY_SECRET="tumhara-ek-aur-random-secret"
docker compose up -d
# open http://127.0.0.1:5001  |  logs: docker compose logs -f  |  stop: docker compose down
```

> **Secrets kabhi mat badalna** ek dafa set karne ke baad — `LICENSE_KEY_SECRET`
> badla to purani license keys dashboard par reveal nahi hongi. `licdata`
> volume me DB + secrets rehte hain, `docker compose down` par bhi safe.

Open in browser:
- `/` — landing page (this is what `cw.raoshahzaib.site` will serve)
- `/signup`, `/login`, `/dashboard` — user accounts & licenses
- `/admin` — admin panel (token = `LICENSE_ADMIN_TOKEN`)

## Admin panel

Login at `/admin/login` with your `LICENSE_ADMIN_TOKEN`. You get:
- **Stats:** total users, revenue (active licenses), active licenses, active devices
- **Licenses:** create (email, plan, machines, days, amount), edit, revoke/unrevoke, delete
  — the full key is shown **once** on creation, copy it then
- **Devices:** see every activated machine, deactivate to free a seat
- **Users:** list with license counts

## Endpoints

| Method | Path | Auth | What |
|---|---|---|---|
| GET | `/` | — | landing page (HTML) |
| GET | `/api/health` | — | service info (JSON) |
| POST | `/api/signup` | — | `{email, password}` → creates account, logs in |
| POST | `/api/login` | — | `{email, password}` → session |
| POST | `/api/logout` | — | clears session |
| GET | `/api/me` | session | account + licenses (key prefix only) |
| POST | `/api/admin/licenses` | `X-Admin-Token` | `{email, plan, max_machines, days, amount_cents}` → full key (**returned once**) |
| POST | `/api/licenses/validate` | — | `{key, machine_id}` → `{valid, plan, expires_at, machines_used}` |
| POST | `/api/licenses/deactivate` | — | `{key, machine_id}` → frees a seat |
| GET | `/api/my/licenses/<id>/key` | session | apni full key reveal (copy ke liye) |

## Try it

```bash
# 1. signup
curl -c jar -X POST localhost:5001/api/signup \
  -H 'Content-Type: application/json' \
  -d '{"email":"test@example.com","password":"secret123"}'

# 2. create a key (admin)
curl -X POST localhost:5001/api/admin/licenses \
  -H 'Content-Type: application/json' -H 'X-Admin-Token: change-me' \
  -d '{"email":"test@example.com","plan":"pro","max_machines":2,"days":365}'

# 3. validate from a machine (use the returned key)
curl -X POST localhost:5001/api/licenses/validate \
  -H 'Content-Type: application/json' \
  -d '{"key":"CW-XXXX-XXXX-XXXX-XXXX","machine_id":"laptop-1"}'
```

## Env vars

| Var | Default | What |
|---|---|---|
| `LICENSE_DB` | `./licenses.db` | sqlite path (Docker: `/data/licenses.db`) |
| `LICENSE_ADMIN_TOKEN` | `change-me` | **change in production** |
| `LICENSE_SESSION_SECRET` | random/boot | set a fixed value in production |
| `LICENSE_KEY_SECRET` | auto-generated | key-encryption secret — **set in production, kabhi mat badalna** (badla to purani keys reveal nahi hongi) |
| `HOST` / `PORT` | `127.0.0.1` / `5001` | bind |

## What's next

- **M2:** login gate + startup validation inside the desktop app (offline grace period).
- **M3:** purchase page + Binance Pay webhook → auto-creates license on payment.
- **Deploy:** this image on the OCI k3s cluster (ArgoCD, like the other apps).
