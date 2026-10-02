# CreatorWatch License Server — M1

Tiny cloud service for accounts + license keys. The desktop app stays
100% local; on startup it will call `POST /api/licenses/validate`
(M2: login gate in the app).

## Dev run

```bash
cd license-server
pip install -r requirements.txt
python app.py        # http://127.0.0.1:5001
```

## Endpoints

| Method | Path | Auth | What |
|---|---|---|---|
| GET | `/` | — | service info |
| POST | `/api/signup` | — | `{email, password}` → creates account, logs in |
| POST | `/api/login` | — | `{email, password}` → session |
| POST | `/api/logout` | — | clears session |
| GET | `/api/me` | session | account + licenses (key prefix only) |
| POST | `/api/admin/licenses` | `X-Admin-Token` | `{email, plan, max_machines, days}` → full key (**returned once**) |
| POST | `/api/licenses/validate` | — | `{key, machine_id}` → `{valid, plan, expires_at, machines_used}` |
| POST | `/api/licenses/deactivate` | — | `{key, machine_id}` → frees a seat |

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
| `HOST` / `PORT` | `127.0.0.1` / `5001` | bind |

## What's next

- **M2:** login gate + startup validation inside the desktop app (offline grace period).
- **M3:** purchase page + Binance Pay webhook → auto-creates license on payment.
- **Deploy:** this image on the OCI k3s cluster (ArgoCD, like the other apps).
