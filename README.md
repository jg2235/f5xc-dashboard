# F5 XC Dashboard

A production-grade read-only SaaS dashboard for **F5 Distributed Cloud (XC)** that periodically pulls configuration and analytics via the XC REST API and surfaces them as visual dashboards.

**Version**: 0.9.0 — Multi-namespace support. See `CHANGELOG.md` for the full release history.

See `CHANGELOG.md` for the full release history.

---

## Features

| Surface | Status |
|---|---|
| FastAPI backend (Python 3.12) | ✅ |
| Celery workers + beat scheduler | ✅ |
| Postgres + TimescaleDB hypertables + continuous aggregates | ✅ |
| Redis (broker + cache) | ✅ |
| Next.js 15 frontend (App Router) | ✅ |
| Local auth (bcrypt + JWT), OIDC stub | ✅ |
| F5XCClient with mock mode + fixtures | ✅ |
| HTTP load balancer inventory + stats | ✅ |
| LB detail (drill-down with policies, advertise targets, pool health, WAF/Bot/API analytics) | ✅ |
| Certificate expiration dashboard (green/amber/red/expired) | ✅ |
| Origin pool inventory + detail UI | ✅ |
| Per-origin per-site healthcheck matrix | ✅ |
| Site cache (RE / CE / virtual) | ✅ |
| Policy visibility — WAF, service, bot, API (shared + local with badges) | ✅ |
| Reverse lookup: which LBs reference each policy | ✅ |
| Alembic migrations | ✅ |
| WAF analytics (sparklines, top-K, recent events) | ✅ |
| Bot analytics (dual source: BD Standard + BD-A, full taxonomy, per-endpoint breakdown) | ✅ |
| API discovery & analytics (ML state, shadow detection, per-endpoint latency p50/p95/p99) | ✅ |
| Security analytics — cross-signal attacker profiles, country choropleth, per-attacker timelines | ✅ |
| Alert engine — 6 rules, in-dashboard inbox, ack/resolve workflow, dedup with occurrence count | ✅ |
| Slack alerting | ⏳ deferred |
| API schema drift detection | ⏳ deferred |







Single F5 XC tenant authentication. **Multi-namespace** support as of v0.9.0 — operators add/remove watched namespaces via `make namespace-add NAMESPACE=foo` (probes F5 XC for existence; persisted in `tenants.namespaces` array column).

---

## Prerequisites

- Docker Engine 24+ with Compose v2 plugin (`docker compose version` must work)
- On WSL2: either enable Docker Desktop's WSL integration, or install Docker's official `docker-ce` repo + enable systemd. See [the Docker Engine install guide](https://docs.docker.com/engine/install/ubuntu/).
- ~2 GB free disk for images
- Ports 3000, 5432, 6379, 8000 available on the host

---

## Quick start

```bash
# 1. Configure
cp .env.example .env
# Edit .env:
#   F5XC_MOCK=true            ← keep true for first boot; fixture data shows the UX
#   JWT_SECRET_KEY=<random>   ← python -c "import secrets; print(secrets.token_urlsafe(48))"

# 2. Bring up the stack (first run pulls ~1.5 GB of images; 2–4 min)
make up

# 3. Seed admin user + tenant + initial sync
SEED_ADMIN_PASSWORD='change_me_now' make seed

# 4. Open
#   Dashboard → https://localhost  (TLS via Caddy; trust the local CA root once)
#   API docs → https://localhost/docs
```

Default login (override via `SEED_ADMIN_USERNAME` / `SEED_ADMIN_PASSWORD` env vars before running `make seed`):
- **Username**: `admin`
- **Password**: `changeme`

### If the admin user already exists

`make seed` is create-only by design — it will not overwrite an existing admin password. Use:

```bash
ADMIN_PASSWORD='new-strong-password' make reset-admin-password
```

### Verify the stack

```bash
docker compose ps
# Expected: all 6 services "Up", postgres/redis/backend "healthy",
# frontend/worker/beat show no healthcheck (correct — they aren't HTTP servers)

curl -k https://localhost/healthz   # → {"status":"ok","version":"0.9.0"}
curl -k https://localhost                    # → Next.js HTML
```

### Switch to live F5 XC data

```bash
# In .env:
F5XC_MOCK=false
F5XC_API_TOKEN=<your-api-token>

docker compose restart backend worker beat
# Trigger a sync from the sidebar "Sync now" button, or:
# v0.7.2: bearer auth replaced with cookie auth.
# Login first to get cookies (saves them to /tmp/c.txt):
curl -k -c /tmp/c.txt -d "username=admin&password=YOUR_PWD" \
  https://localhost/api/v1/auth/login
# Then call protected endpoints with the cookie + CSRF header:
CSRF=$(awk '/f5xc_csrf/ {print $7}' /tmp/c.txt)
curl -k -b /tmp/c.txt -X POST -H "X-CSRF-Token: $CSRF" \
  https://localhost/api/v1/sync/all
```

---

## Repo layout

```
f5xc-dashboard/
├── docker-compose.yml        # All services
├── Makefile                  # up / down / seed / reset-admin-password / test / lint / clean
├── .env.example
├── CHANGELOG.md
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pyproject.toml        # ruff + pytest config
│   ├── app/
│   │   ├── main.py           # FastAPI factory
│   │   ├── config.py         # pydantic-settings
│   │   ├── db.py             # SQLAlchemy session
│   │   ├── logging_config.py # structlog
│   │   ├── api/              # auth, health, loadbalancers, certificates, sync
│   │   ├── auth/             # providers (Local + OIDC stub), JWT, deps
│   │   ├── f5xc/
│   │   │   ├── client.py     # F5XCClient (httpx + tenacity + mock)
│   │   │   ├── transformers.py
│   │   │   └── fixtures/     # mock JSON for offline / sandbox dev
│   │   ├── models/           # Tenant, User, LoadBalancer, Certificate, OriginPool
│   │   ├── schemas/          # Pydantic
│   │   └── workers/          # Celery app + beat + tasks
│   ├── scripts/
│   │   ├── seed.py                  # create tenant + admin (idempotent, no-op if exists)
│   │   └── reset_admin_password.py  # force-reset admin password
│   └── tests/                # 9 unit tests, all passing
│
├── frontend/
│   ├── Dockerfile            # multi-stage, standalone Next.js build
│   ├── next.config.js        # /api/* proxy to backend (runtime env)
│   ├── package.json          # Next 15, React 19, TanStack Query, Recharts
│   ├── tailwind.config.js
│   ├── public/.gitkeep
│   └── src/
│       ├── app/              # App Router: /, /login, /loadbalancers, /certificates
│       ├── components/ui/    # Card, Badge, Shell, StatCard
│       └── lib/              # api client, cn, useRequireAuth
│
├── infra/init-db.sql         # TimescaleDB + pgcrypto extensions
└── docs/
    ├── ARCHITECTURE.md
    └── OIDC.md               # roadmap for OIDC provider wiring
```

---

## How it works

1. **Celery Beat** schedules periodic polls against F5 XC (every 10 min for config, configurable per-dataset via `POLL_*_INTERVAL` env vars).
2. **Celery Workers** execute sync tasks that call `F5XCClient.list_*()`, transform responses with `extract_*_fields()`, and UPSERT into Postgres on `(tenant_id, namespace, name)`.
3. **FastAPI** serves the dashboard API — JWT-authenticated endpoints that return flattened summary rows from the DB plus aggregate stats.
4. **Next.js** hits the API via TanStack Query. The browser calls `/api/v1/*` on its own origin; Next.js's `rewrites()` proxies those to `http://backend:8000` on the Docker Compose network.

### Mock mode

`F5XC_MOCK=true` routes all GET calls to JSON fixtures under `backend/app/f5xc/fixtures/`. Fixtures include real self-signed PEMs with known expirations so cert-status classification exercises end-to-end without a live tenant.

### Read-only guarantee

v1 never issues `POST` / `PUT` / `DELETE` against F5 XC. `F5XCClient` does not expose mutation methods; the mock client explicitly no-ops any non-GET. Sync triggers in the API (`/sync/*`) only re-run read-based pulls. Write enablement is deferred to a future slice with explicit config-change audit log and RBAC review.

---

## Troubleshooting

### Login returns 500 "Internal Server Error" on the login page

The frontend's proxy rewrite can't reach the backend. Diagnose:

```bash
docker compose logs frontend --tail=20
# Look for: Failed to proxy ... ECONNREFUSED

docker compose exec frontend printenv | grep API_BASE_URL
# Expected: API_BASE_URL=http://backend:8000

docker compose exec frontend wget -qO- http://backend:8000/api/v1/healthz
# Expected: {"status":"ok"}
```

If `API_BASE_URL` is wrong, it's been overridden in your `.env`. Set it correctly (or remove it so the compose default applies) and rebuild:

```bash
docker compose up -d --build --no-deps frontend
```

### "unhealthy" on worker or beat

Should not happen in v0.1.1 — `healthcheck: disable: true` is set for both. If you see it, confirm your `docker-compose.yml` matches the one shipped.

### Login fails with 401 after `make seed` changes

`make seed` does not update existing admin passwords. Use `make reset-admin-password`.

### `docker compose up` fails on frontend with "/app/public": not found

Missing `frontend/public/.gitkeep`. Create it:

```bash
mkdir -p frontend/public && touch frontend/public/.gitkeep
make up
```

---

## Testing

```bash
make test          # backend unit tests (9 tests)
make lint          # ruff check
```

All tests run against mock fixtures — no F5 XC credentials needed for CI.

---

## Configuration reference

See `.env.example`. Key knobs:

| Variable | Default | Purpose |
|---|---|---|
| `F5XC_MOCK` | `true` | Toggle live vs fixture mode |
| `F5XC_TENANT` | `<your-tenant>` | Tenant subdomain (substituted into URL template) |
| `F5XC_API_URL_TEMPLATE` | `https://{tenant}.console.ves.io` | Tenant URL pattern. Switch to `https://{tenant}.ves.volterra.io` for legacy/enterprise tenants. |
| `F5XC_NAMESPACE` | `<your-namespace>` | Namespace to scan |
| `F5XC_API_TOKEN` | — | API token with read scope on the namespace |
| `POLL_CONFIG_INTERVAL` | `600` | Seconds between config-object polls |
| `POLL_ANALYTICS_INTERVAL` | `300` | Seconds between analytics polls (future slices) |
| `CERT_WARN_DAYS` | `30` | Amber threshold |
| `CERT_CRITICAL_DAYS` | `7` | Red threshold |
| `AUTH_PROVIDER` | `local` | `local` or `oidc` (oidc is stub; see docs/OIDC.md) |
| `JWT_SECRET_KEY` | — | Must be set to random long string in prod |

`API_BASE_URL` is set in `docker-compose.yml` (not `.env`) because it's container-network-specific.

---

## Roadmap

| Slice | Scope |
|---|---|
| 0 | Foundation, auth, F5XCClient, mock mode ✅ |
| 1 | LB/FQDN inventory + cert expiration ✅ |
| 2 | Origin pool UI + per-origin per-site healthcheck matrix ✅ |
| 3 | Applied policies detail view (WAF, service, bot, API) + Alembic ✅ |
| 4 | WAF statistics (TimescaleDB hypertables, sparklines, top-K) ✅ |
| 5 | Bot statistics (dual source, full taxonomy, per-endpoint) ✅ |
| 6 | API statistics + ML discovery state + shadow detection ✅ |
| 7 | Security analytics + in-dashboard alerting (cross-signal, geo, attacker timelines, alert engine) ✅ |
| — | Slack/email alerting; schema drift detection; OIDC activation; per-namespace token isolation |

---

## Security notes

- Single F5 XC tenant authentication. Multi-namespace within that tenant.
- TLS termination via Caddy; backend/frontend/postgres/redis bound to the docker network only (no host ports).
- Cookie-based auth with CSRF double-submit; `httpOnly` + `Secure` + `SameSite=Strict`.
- JWT access TTL 15 min; revocation list in Redis; refresh rotation.
- Login rate limiting via slowapi (default 5/15min per source IP).
- F5 XC API token stored in `secrets/f5xc_api_token` (Docker secret) or env var; not in DB.
- Bcrypt cost is the passlib default (12).
- Change the seed `admin/changeme` password immediately after first login — use `make user-rotate-password TARGET_USER=admin`.


## Multi-namespace operations

The dashboard authenticates against ONE F5 XC tenant with ONE token but watches MULTIPLE namespaces within that tenant. Operators manage the watch list via:

```bash
make namespace-list                                  # show watched namespaces
make namespace-add NAMESPACE=foo                     # probe F5 XC + append
make namespace-remove NAMESPACE=foo                  # refuses to leave list empty
make namespace-replace NAMESPACES="shared,foo,bar"   # bulk replace
```

Probe-on-add hits `/api/web/namespaces/{name}` to validate the namespace exists in F5 XC (catches typos and RBAC issues at write time).

## TLS deployment

The dashboard runs HTTPS-only via a Caddy reverse proxy on ports 80 and
443. Backend, frontend, postgres, redis listen only on the internal docker
network; there is no path that bypasses TLS.

### Local / development

`infra/caddy/Caddyfile` ships with `tls internal` pinned to `localhost`.
On first start, Caddy generates a self-signed cert from a local CA. Trust
the CA root once and the browser stops warning:

```bash
docker exec f5xc-dashboard-caddy-1 \
  cat /data/caddy/pki/authorities/local/root.crt > caddy-root.crt
# Then import caddy-root.crt into:
#   - macOS: Keychain Access → System → Certificates → drag-and-drop, mark trusted
#   - Windows: certmgr.msc → Trusted Root Certification Authorities → Import
#   - Linux: /usr/local/share/ca-certificates/ + sudo update-ca-certificates
#   - Firefox: about:preferences#privacy → View Certificates → Authorities → Import
```

Visit `https://localhost/`.

### Production (ACME)

Edit `infra/caddy/Caddyfile`:

```diff
- localhost {
-   tls internal
+ dashboard.example.com {
+   tls ops@example.com
```

Ensure DNS A/AAAA for `dashboard.example.com` points to the host, and
that ports 80 + 443 are reachable from the public internet for the
HTTP-01 ACME challenge. Restart Caddy:

```bash
docker compose restart caddy
docker compose logs -f caddy   # watch certificate issuance
```

## Container reload semantics

What command picks up which kind of change:

| Change | Command |
|---|---|
| Backend Python code | uvicorn `--reload` watcher auto-reloads |
| Backend dependency change (`requirements.txt`) | `docker compose build backend && docker compose up -d backend` |
| Frontend `.tsx` / `.ts` (with hot-reload running) | auto |
| Tailwind config / new tailwind classes | `make rebuild-frontend` |
| `package.json` | `make rebuild-frontend` |
| `.env` change | `docker compose up -d` |
| Alembic migration | backend lifespan runs migrations on startup; `docker compose restart backend` |
| `secrets/<file>` change | `docker compose up -d --force-recreate backend worker beat` |
| `infra/caddy/Caddyfile` change | `docker compose restart caddy` |
| `docker-compose.yml` change (ports, env, secrets, volumes) | `docker compose up -d` (compose detects and recreates only what changed) |

`docker compose restart <svc>` is faster than `up -d` but doesn't re-read
the compose file. If you change ports, volumes, secrets, or environment,
use `up -d`.
