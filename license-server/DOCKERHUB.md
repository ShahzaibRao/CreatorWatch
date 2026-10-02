# CreatorWatch License Server

Accounts + license keys for the [CreatorWatch](https://github.com/ShahzaibRao/CreatorWatch)
desktop app. A tiny Flask service: user signup/login, per-machine license
validation, and an admin panel for creating/revoking keys. The desktop app
itself stays 100% local — on startup it just calls this API to unlock.

## How to use this image

### Quick start (SQLite — zero config)

```console
$ docker run -d --name lic -p 5001:5001 \
    -e LICENSE_ADMIN_TOKEN=change-me \
    -v licdata:/data \
    <dockerhub-username>/creatorwatch-license:latest
```

Open [http://localhost:5001](http://localhost:5001), sign up, then create
license keys from `/admin`.

### Production (Postgres)

```console
$ docker run -d --name lic -p 5001:5001 \
    -e DATABASE_URL=postgresql://user:pass@dbhost:5432/creatorwatch \
    -e LICENSE_ADMIN_TOKEN=<strong-secret> \
    -e LICENSE_SESSION_SECRET=<stable-random> \
    -e LICENSE_KEY_SECRET=<stable-random-never-change-this> \
    -e SITE_DOMAIN=keys.example.com \
    -e SITE_NAME=CreatorWatch \
    -v licdata:/data \
    <dockerhub-username>/creatorwatch-license:latest
```

Set `DATABASE_URL` for Postgres; leave it empty for the built-in SQLite.

### Docker Compose

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: creatorwatch
      POSTGRES_USER: creatorwatch
      POSTGRES_PASSWORD: changeme
    volumes:
      - pgdata:/var/lib/postgresql/data
  license-server:
    image: <dockerhub-username>/creatorwatch-license:latest
    ports:
      - "5001:5001"
    environment:
      DATABASE_URL: postgresql://creatorwatch:changeme@db:5432/creatorwatch
      LICENSE_ADMIN_TOKEN: change-me
    volumes:
      - licdata:/data
    depends_on:
      - db
volumes:
  licdata:
  pgdata:
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | _(empty)_ | Postgres URL. Empty = built-in SQLite |
| `LICENSE_DB` | `./licenses.db` | SQLite path when `DATABASE_URL` is empty (Docker: `/data/licenses.db`) |
| `LICENSE_ADMIN_TOKEN` | `change-me` | **Change in production** — `/admin` login |
| `LICENSE_SESSION_SECRET` | random per boot | Set a fixed value in production |
| `LICENSE_KEY_SECRET` | auto-generated file | Encrypts license keys at rest — **set in production, never change it afterwards** |
| `SITE_DOMAIN` / `SITE_NAME` | _(empty)_ / `CreatorWatch` | Your domain + brand (no hardcoding) |
| `HOST` / `PORT` | `0.0.0.0` / `5001` | Bind address |

## Persistent data

`/data` holds the SQLite file and the auto-generated key secret — mount a
volume so they survive container restarts. With Postgres, the database lives
outside the container.

## Image tags

- `latest` — newest build from the `cloud` branch
- `vX.Y.Z` (e.g. `v0.5.4`) — server image from that app-release era (rollback-friendly)
- `license-server-v*` — manual immutable releases

Multi-arch: `linux/amd64` + `linux/arm64`.
