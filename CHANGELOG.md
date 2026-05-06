# Changelog

## v0.9.0 — Multi-namespace support (2026-05-06)

The dashboard authenticates against ONE F5 XC tenant with ONE token, but
now watches MULTIPLE namespaces within that tenant. Operators add or
remove namespaces from the watch list via a new ops CLI; sync tasks
iterate the configured list instead of a single namespace.

### Multi-namespace

- **`tenants.namespaces` ARRAY column** (alembic `0011_tenant_namespaces`).
  Authoritative list of namespaces watched per tenant. Existing rows
  populated with `{shared, <legacy f5xc_namespace>}` to preserve
  pre-v0.9.0 behavior — `sync_certificates` and `sync_policies` had
  hardcoded `["shared", tenant.f5xc_namespace]` literals; the array
  column makes the equivalent explicit and operator-controlled.
- **`Tenant.effective_namespaces` property** returns `namespaces` if
  populated, else `[f5xc_namespace]` as fallback. Sync tasks read
  through the property; the legacy `f5xc_namespace` column stays one
  release for rollback safety, scheduled for removal in v0.10.0.
- **4 sync tasks refactored** to iterate `effective_namespaces`:
  `sync_loadbalancers`, `sync_origin_pools` (single-namespace → multi),
  `sync_certificates`, `sync_policies` (literal → operator-controlled).
  9 other tasks inherit multi-namespace correctness via per-LB iteration
  from the DB (LB rows carry their own namespace; once `sync_loadbalancers`
  populates LBs from all watched namespaces, downstream tasks just work).
- **Per-namespace failure isolation**: each namespace's list call is
  wrapped in try/except. RBAC failures or transient errors against one
  namespace don't break sibling namespaces. Reaping is scoped to
  successfully-listed namespaces only — a failed list against `shared`
  doesn't wipe `<your-namespace>` data.

### Operational

- **New ops CLI** for namespace management (CLI-only by design, no API):
  - `make namespace-list` — show watched namespaces
  - `make namespace-add NAMESPACE=foo` — probe + append
  - `make namespace-remove NAMESPACE=foo` — refuses to leave list empty
  - `make namespace-replace NAMESPACES="a,b,c"` — bulk replace
- **Probe-on-add** validates namespace exists in F5 XC by hitting
  `/api/web/namespaces/{name}` (the namespace registry endpoint, which
  404s on non-existent namespaces). List-style endpoints like
  `list_http_load_balancers` accept bogus namespaces and return empty;
  the registry endpoint is strict. Catches typos and RBAC issues at
  write time, not at the next sync cycle.
- **Last-namespace protection**: `make namespace-remove` refuses to
  remove the only remaining namespace (the dashboard would have nothing
  to sync). Operator can `make namespace-replace` to swap if intentional.
- **New ops CLI for users** (decoupled from multi-namespace work but
  shipped in this release): `make user-{list,get,add,rotate-password,
  set-role,deactivate,activate}`. Last-active-admin protection on
  deactivate and demote prevents zero-admin lockouts. CLI-only, no
  admin REST API.

### Schema

- `0010_drop_token_ciphertext` — drops the `f5xc_api_token_ciphertext`
  column added in an abandoned multi-tenant attempt earlier in the
  development cycle. Net schema change for v0.9.0 alone is
  `0008 → 0011_tenant_namespaces`; 0009 and 0010 are visible in
  `alembic history` for traceability.

### Operational gotchas worth knowing

- **Stale-row reaping is scoped to currently-watched namespaces, not
  historically-watched.** Removing a namespace from the watch list does
  NOT auto-delete its synced rows from `load_balancers`, `origin_pools`,
  `certificates`, `app_firewalls`, etc. The data goes stale silently.
  Operators clean up manually via `make truncate-synced-data` or
  targeted SQL. Auto-deletion on namespace removal would be surprising
  and destructive; the conservative default avoids data loss when an
  operator removes a namespace temporarily for debugging.

- **`F5XC_NAMESPACE` env var stays singular.** Backward compatible with
  pre-v0.9.0 deployments. `seed.py` wraps it in a single-element list
  when populating the new `namespaces` column. To watch additional
  namespaces post-seed, use `make namespace-add NAMESPACE=foo`. There
  is no plural `F5XC_NAMESPACES` env var.

- **Alembic revision IDs are capped at 32 characters.** Postgres'
  `alembic_version.version_num` column is `VARCHAR(32)`. Long revision
  IDs (e.g., `0010_drop_tenant_token_ciphertext` = 34 chars) cause the
  upgrade transaction to fail at the version-stamp UPDATE, rolling back
  any DDL the migration applied. Convention going forward:
  `<NNNN>_<short_descriptor>` ≤ 32 chars.

- **`alembic revision --rev-id <slug> -m "<msg>"` appends the message
  slug to the FILENAME** even when `--rev-id` is set. The internal
  revision ID is correct, but the file is named
  `<rev-id>_<message-slug>.py`. Rename post-generation to keep filenames
  matching project convention.

- **F5 XC list endpoints are LENIENT about namespace existence.** They
  return 200 + empty list for non-existent namespaces. Use the namespace
  registry endpoint (`/api/web/namespaces/{name}`) for strict existence
  validation — 404s on bogus names. This was discovered during probe-on-add
  testing; the initial probe used `list_http_load_balancers` and
  silently accepted typos.


## v0.8.0 — Auth-token correctness, sync hygiene, JWT revocation (2026-05-05)

This release is split between auth/security improvements (shorter access
TTL, JWT revocation list, startup auth probe), sync correctness (stale-row
reaping, env-over-DB token precedence), and operational hygiene
(`ANALYTICS_ENABLED` gate to silence 404s on tenants without the analytics
module). Two latent bugs from earlier releases were also fixed along the way.

### Security

- **JWT access token TTL reduced to 15 min** (was 60). `JWT_ACCESS_TOKEN_EXPIRES_MINUTES=15`.
  Narrows the window for stolen-token reuse.

- **JWT revocation list** backed by Redis sorted set `jwt_revoked` (key:
  `jti`, score: token `exp` Unix timestamp). Logout writes both the
  access and refresh `jti` to the blocklist; refresh rotation revokes
  the OLD refresh token's `jti` before issuing a new pair. Per-request
  revocation check in `auth/dependencies.get_current_user` is **fail-closed**
  on Redis unreachable (returns 503) — consistent with rate-limit and
  worker-queue dependencies. Daily celery task
  `app.workers.tasks.jwt_gc.gc_revoked_jtis` removes entries whose tokens
  have already expired.

  Backward compatibility: tokens issued before v0.8.0 lack the `jti`
  claim and skip the revocation check, expiring naturally at their TTL.
  No forced re-login on deploy.

- **Startup F5 XC auth probe** (`f5xc_auth_probe_ok`/`_failed`/`_timeout`).
  Backend lifespan calls `list_sites()` against F5 XC with a hard 5-second
  timeout. Surfaces auth misconfiguration (expired/wrong token) before
  the first sync runs. Warn-only — does not block startup.

### Sync correctness

- **Stale-row reaping** in 7 inventory sync tasks: `load_balancers`,
  `origin_pools`, `sites`, `certificates`, `policies` (4 tables), `api_endpoints`,
  `api_discovery_states`. Pattern: capture `sync_started_at` at per-tenant
  scope, post-iteration `DELETE WHERE last_seen_at < sync_started_at`
  (or `updated_at` for tables without `last_seen_at`). Guarded on at
  least one source succeeding, so transient API failures don't wipe
  legitimate cached rows. First run reaped 4 zombie sites that had
  drifted out of F5 XC.

- **F5 XC API token precedence flipped to env > DB.** `settings.f5xc_api_token`
  now takes precedence over `tenant.f5xc_api_token` across all 13 sync
  tasks. Enables token rotation via env var alone (no DB write). The
  `tenants.f5xc_api_token` column is now nullable
  (alembic `0008_tenant_token_nullable`).

### Operational

- **`F5XC_ANALYTICS_ENABLED` setting** (default `True`, env
  `F5XC_ANALYTICS_ENABLED`). Set to `false` for tenants without the F5 XC
  analytics module licensed to suppress 8 sync tasks that hit `/api/data/*`
  endpoints. Eliminates 404 noise (84 errors/cycle on the local test tenant
  → 0). Each gated task logs a structured `*_skipped_analytics_disabled`
  event when it ticks.

### Fixed

- **Alembic logger detach** (latent bug): `fileConfig()` in
  `backend/alembic/env.py` was hijacking the root logger handlers via
  `alembic.ini`'s `[logger_root] handlers = console`, silently detaching
  the structlog handlers set up at app startup. As a result, all log lines
  emitted after `run_migrations()` returned (probe outcome,
  `f5xc_dashboard_startup`) silently disappeared from docker logs.
  Skipped `fileConfig` entirely in `env.py`.

- **Audit cleanup task never executed** (latent v0.7.2 bug): the
  `audit.cleanup_audit_events` task was registered in
  `celery_app.beat_schedule` but missing from celery's `include=[]`
  list. Worker silently no-op'd beat-queued instances of the task.
  In practice the audit table only had 18 rows (64 KB) when found,
  so operational impact was nil — but the bug went unnoticed since
  v0.7.2 ship. Added to include list.

### Operational gotchas worth knowing

- **`docker compose restart` does NOT reload `.env`.** Containers retain
  the env they were created with. Use `docker compose up -d --force-recreate <service>`
  to pick up `.env` changes.

- **`--force-recreate` must hit ALL services** that read the changed
  setting, not just the obvious one. We initially recreated worker+beat
  for `F5XC_ANALYTICS_ENABLED=false` and forgot backend, leaving its
  `Settings.analytics_enabled` reading the default `True` until backend
  was also recreated.

## v0.7.2 — Security hardening (2026-05-01)

End-to-end security hardening of the dashboard: cookie-based auth replaces
bearer tokens in the browser, TLS termination via Caddy reverse proxy,
Docker secrets for sensitive credentials, audit logging, login rate
limiting, and security response headers. Plaintext secrets removed from
`.env` and from container environment listings.

### Security (breaking)

- **Cookie-based auth replaces `Authorization: Bearer`.** Access and refresh
  tokens are now `httpOnly` + `Secure` + `SameSite=Strict` cookies set by
  the backend. The SPA no longer touches `localStorage` for tokens. CSRF
  protection via double-submit cookie + `X-CSRF-Token` header on mutating
  requests. Login response carries `{user}` only — no token returned to
  the client.
- **Login rate limiting** via slowapi (`AUTH_LOGIN_RATE_LIMIT`, default
  `5/15minutes` per source IP). Exceeding the limit returns 429.
- **Security response headers**: HSTS (when on TLS), `X-Content-Type-Options
  nosniff`, `X-Frame-Options DENY`, `Referrer-Policy
  strict-origin-when-cross-origin`, `Permissions-Policy`, and
  `Content-Security-Policy default-src 'none'` for JSON API responses.
- **CORS scoped** to `CORS_ALLOW_ORIGINS` (was `*`). Same-origin deployment
  via Caddy uses an empty origin list (no CORS preflight). `allow_credentials=True`
  required for cookie auth, so wildcard origins are rejected.
- **TLS termination via Caddy reverse proxy.** Backend, frontend, postgres,
  and redis no longer expose ports to the host. Caddy on 80/443 is the
  sole ingress. Local dev uses `tls internal` (self-signed); production
  swaps to ACME via Let's Encrypt.
- **Docker secrets** for `JWT_SECRET_KEY`, `F5XC_API_TOKEN`, and
  `POSTGRES_PASSWORD`. Values are read from `/run/secrets/<key>` and
  bootstrapped into `os.environ` before pydantic loads `Settings`.
  `scripts/bootstrap-secrets.sh` generates secrets with correct perms
  (700 on dir, 600 on files).
- **Production safety check at startup.** When `F5XC_MOCK=false`, the app
  refuses to boot if `JWT_SECRET_KEY` is the default placeholder or shorter
  than 32 chars, if `F5XC_API_TOKEN` is empty, or if
  `SESSION_COOKIE_SECURE=false`.
- **Audit log** (`audit_events` table). Records `auth.login.success`,
  `auth.login.failure`, `auth.logout`, `auth.refresh` with IP, user agent,
  and JSONB details. Retention configurable via `AUDIT_RETENTION_DAYS`
  (default 180), enforced by daily celery beat task
  `audit.cleanup_audit_events`.
- **F5 XC error sanitization** — upstream response bodies are no longer
  echoed in HTTP error responses to clients; full detail goes to logs.
- **Postgres + Redis no longer publicly bound** to host. Reachable only
  via the docker network. `docker compose exec postgres psql ...` still
  works for ops; host-side `psql -h localhost` does not.

### Added

- `app/middleware/security_headers.py` — `SecurityHeadersMiddleware`.
- `app/auth/{cookies,audit}.py` — cookie helpers, audit recorder.
- `app/auth/dependencies.py` — `get_current_user` reads from session
  cookie; new `csrf_protect` dependency for mutating routes.
- `app/auth/security.py` — adds `create_refresh_token`,
  `decode_access_token`, `decode_refresh_token`, `generate_csrf_token`,
  `constant_time_compare`.
- `app/api/auth.py` — `/login`, `/refresh`, `/logout`, `/me` endpoints,
  rate-limited via `@limiter.limit`.
- `app/schemas/auth.py` — `LoginResponse`, `UserOut`.
- `app/models/audit_event.py` — `AuditEvent` ORM model.
- `app/workers/tasks/audit_cleanup.py` — daily retention enforcement.
- `alembic/versions/0007_audit_events.py` — table migration.
- `infra/caddy/Caddyfile` — TLS + reverse proxy, pinned to `localhost`
  for dev.
- `scripts/bootstrap-secrets.sh` — generate or rotate Docker secrets.
- `backend/scripts/entrypoint.sh` — substitutes postgres password from
  `/run/secrets/postgres_password` into `DATABASE_URL` at container start.
- `docs/SECURITY.md` — threat model + posture.
- Makefile targets: `backup-db`, `restore-db`, `rotate-jwt`, `rotate-token`,
  `audit-tail`, `logs-tail`, `truncate-synced-data`, `rebuild-frontend`,
  `clean-bak`, `generate-secrets`.

### Changed

- `app/main.py` — slowapi + 429 handler, `SecurityHeadersMiddleware`,
  scoped CORS, `validate_production_safe()` lifespan check, F5XCError
  sanitizer.
- `app/config.py` — `_bootstrap_secrets()` helper, JWT/cookie/CSRF/CORS/
  audit-retention/rate-limit fields, `validate_production_safe()` method,
  `cors_origins_list` property.
- `docker-compose.yml` — caddy service with TLS; top-level `secrets:`
  block; secrets mounts on backend, worker, beat, postgres; postgres
  uses `POSTGRES_PASSWORD_FILE`; `__PG_PWD__` placeholder substituted by
  entrypoint shim; backend/frontend/postgres/redis lose public ports.
- `frontend/src/lib/api.ts` — auth core swapped from bearer/localStorage
  to cookies/CSRF; `request()` adds `credentials: 'include'`, attaches
  CSRF on mutating methods, auto-refreshes on 401 with single retry.
- `frontend/src/lib/useRequireAuth.ts` — calls `/me` instead of reading
  `localStorage`.
- `frontend/src/app/login/page.tsx` — drops `auth.setToken(...)`;
  cookies set by server, page just navigates.
- `requirements.txt` — adds `slowapi==0.1.9`.

### Fixed

- `record_audit()` now `db.commit()`s instead of `db.flush()` — the
  bundle's flush-only pattern caused audit rows to roll back when the
  request session closed.
- `api/auth.py` does not use `from __future__ import annotations` — the
  combination with slowapi's `@limiter.limit` wrapper and Pydantic v2's
  `get_type_hints` produces `TypeError: ForwardRef('OAuth2PasswordRequestForm')
  is not a callable`.

### Deferred to v0.8.0

- JWT revocation list (refresh-token rotation issues new `jti`; no
  active blocklist yet).
- Token-precedence flip: env over DB-stored `tenant.f5xc_api_token`.
- Drop `NOT NULL` on `tenants.f5xc_api_token`.
- Stale-row reaping in sync tasks.
- Startup auth probe (warn-only) against F5 XC.
- `ANALYTICS_ENABLED` knob to silence data-plane 404 noise on tenants
  without analytics.
- Backend Dockerfile non-root user (UID 10001).

### Migration notes

- `make generate-secrets` to bootstrap `secrets/{jwt_secret_key,
  f5xc_api_token, postgres_password}`. The script prompts for the F5 XC
  token; JWT and postgres passwords are auto-generated.
- Strip `JWT_SECRET_KEY`, `F5XC_API_TOKEN`, `POSTGRES_PASSWORD` from
  `.env` after the secrets are in place. Compose reads them from
  `/run/secrets/*`.
- Rotate the running postgres password to match `secrets/postgres_password`:
  `docker compose exec postgres psql -U f5xc -d f5xc_dashboard \
    -v new_pwd="$(cat secrets/postgres_password | tr -d '\n')" \
    -c "ALTER USER f5xc WITH PASSWORD :'new_pwd';"`
- Trust the Caddy CA root once on the host so the browser stops warning:
  `docker exec f5xc-dashboard-caddy-1 cat /data/caddy/pki/authorities/local/root.crt > caddy-root.crt`
  then import into the OS trust store.
- After cutover the dashboard is at `https://localhost`. The legacy
  `http://localhost:3000` and `http://localhost:8000` URLs no longer work.

## v0.7.1 — Hotfix (2026-04-29)

Configurable F5 XC tenant URL template — supports both modern
(`<tenant>.console.ves.io`) and legacy (`<tenant>.ves.volterra.io`)
URL conventions. Previously the URL was hardcoded, breaking live mode
on tenants that resolve to `ves.volterra.io`.

### Added

- New env var `F5XC_API_URL_TEMPLATE`. Default
  `https://{tenant}.console.ves.io` preserves prior behavior. The
  `{tenant}` placeholder is substituted with `F5XC_TENANT` at client
  construction.
- 3 unit tests covering default, legacy volterra.io, and arbitrary
  custom URL templates (private/airgap).

### Changed

- `F5XCClient.__init__` accepts `api_url_template` parameter.
- `Settings.f5xc_base_url` property now formats from the template.
- `get_f5xc_client()` factory plumbs the template through.
- All 13 sync tasks pass `api_url_template=settings.f5xc_api_url_template`
  through to their inline `F5XCClient(...)` constructions.
- `.env.example` documents both URL conventions inline with a curl
  one-liner to verify which one resolves for a given tenant.
- `README.md` env table updated.

### Migration notes

**v0.7.0 → v0.7.1 in-place upgrade for legacy tenant URLs**:

```bash
# Edit your .env to add the line:
F5XC_API_URL_TEMPLATE=https://{tenant}.ves.volterra.io

# Restart with up -d (recreates containers, re-reads env_file)
cd ~/f5xc-dashboard
docker compose down
docker compose up -d --build
```

If you don't add the new variable, the default
`https://{tenant}.console.ves.io` applies — same as v0.7.0 behavior.

### Test counts

- Backend: 99/99 passing (was 96, +3 new).

---

## v0.7.0 — Slice 7 (2026-04-29)

Security analytics + in-dashboard alerting. Cross-signal correlation joins
WAF, Bot, and API events by source IP + ASN + country into a unified attacker
profile view, with country-level geographic distribution and a 6-rule alert
engine driving an in-dashboard inbox with ack/resolve workflow.

### Decisions locked from slice 7 question round

| Question | Answer | Notes |
|---|---|---|
| 1. Attacker correlation | B — IP + ASN + country | Operator-friendly grouping; full fingerprinting deferred |
| 2. Geo granularity | A — country-level only | Choropleth-style distribution, no city-level pins |
| 3. Attacker drill-down depth | B — per-IP timeline | No risk scoring (subjective weights) |
| 4. Schema drift | A — skip | ~30% scope reduction, deferred to a possible slice 8 |
| 5. Alert channels | A — in-dashboard only | No Slack webhook, no email |
| 6. Time window | A — 24h default + standard picker | Same UX as slices 4–6 |

### Added

- **Two new tables** (no new hypertables):
  - `attacker_profiles` — cross-signal correlator cache. Identity is
    `(tenant_id, source_ip, source_asn, source_country)`. Stores per-signal
    counts (waf_block / waf_monitor / bot_block / bot_challenge / api_4xx),
    total_events, top_endpoint, top_signature, distinct LB count, first/last
    seen. Refreshed every analytics cycle (5 min default) over the
    profile window (24h default).
  - `alerts` — persistent alert log. Identity is
    `(tenant_id, rule_id, dedupe_key)`. Status: open / acknowledged / resolved.
    Re-firing the same rule for the same key bumps `occurrence_count` and
    updates `last_seen_at`; first_seen_at and ack/resolve state are preserved.

- **Cross-signal correlator** (`app/security/correlator.py`):
  - `correlate_attackers()` reads from waf_events + bot_events for the window,
    groups by IP+ASN+country tuple, builds `AttackerAggregates` per group
    (per-signal counts, top endpoint, top signature, set of distinct LBs,
    first/last seen). Truncates to `SECURITY_MAX_ATTACKERS_PER_CYCLE` (default
    2000) keeping the highest-volume.
  - `upsert_attacker_profiles()` writes the cache via Postgres ON CONFLICT
    UPDATE with `func.greatest()` / `func.least()` for first/last seen merge.
  - `attacker_timeline()` builds the chronological event log per IP for the
    drill-down page — merges WAF and Bot events sorted descending.
  - **API 4xx attribution caveat**: `api_metrics_1min` has no source_ip
    dimension, so API 4xx counts per attacker are approximated from WAF
    events with response_code in 400–499. Documented limitation.

- **Alert rule engine** (`app/security/alerting.py`):
  - 6 default rules with per-rule on/off env flags:
    - `waf.block_burst` (warning) — peak WAF blocks/min/lb in last 5min above
      threshold (default 50). Dedupe per LB.
    - `waf.new_attacker` (info) — top-10 WAF blocker IP in last 1h not seen
      in prior 24h. Dedupe per IP.
    - `bot.cred_stuffing` (critical) — per-IP challenge_failed rate >50%
      with ≥20 attempts in last 10min. Dedupe per IP.
    - `api.state_change` (info) — F5 XC ML lifecycle transition (learning
      → mature, etc.). Dedupe per LB+state.
    - `api.shadow_emergence` (warning) — shadow endpoint with ≥100 samples
      and first_seen within last 24h. Dedupe per endpoint.
    - `cert.expiry` (warning/critical) — cert expiring within configured
      days (default 7). Severity escalates to critical at ≤1 day or expired.
      Dedupe per cert.
  - Per-rule exception isolation: a failure in one rule doesn't affect
    others.
  - Alert dedup via Postgres ON CONFLICT — second firing increments
    occurrence_count, updates last_seen_at + description + context, but
    preserves status/ack/resolve state.

- **Two new Celery tasks**:
  - `refresh_attacker_profiles` (every `POLL_ANALYTICS_INTERVAL`, default 5min)
  - `evaluate_alert_rules` (every `POLL_ANALYTICS_INTERVAL`)
  - Plus `cleanup_old_alerts` (daily) — deletes resolved alerts older than
    `ALERT_RETENTION_DAYS` (default 90).

- **API endpoints** under `/api/v1/analytics/security`:
  - `GET /overview` — tenant cross-signal summary (attacker count, countries
    seen, top country, WAF blocks, bot interventions, API 4xx, alert counts)
  - `GET /geo` — country-level event counts for choropleth (filterable by
    signal: all/waf/bot)
  - `GET /attackers` — sortable attacker profile list (sort: total / waf /
    bot / last_seen, optional country filter)
  - `GET /attackers/{ip}/timeline` — chronological event timeline per IP

- **Alerts API** under `/api/v1/alerts`:
  - `GET /` — paginated list (filter by status / severity / rule_id)
  - `GET /summary` — counts by status + severity
  - `GET /{id}` — alert detail
  - `POST /{id}/acknowledge` — transition open → acknowledged
  - `POST /{id}/resolve` — transition open|acknowledged → resolved
  - `POST /{id}/reopen` — transition any → open

- **New routes / UI components**:
  - `/analytics/security` — main dashboard. 4 hero stats (active attackers /
    WAF blocks / bot interventions / open alerts) + 2-column grid (geo
    distribution + open alerts side-list) + sortable attacker profile table
    with cross-signal columns + time-window picker (1h/6h/24h/7d).
  - `/analytics/security/attackers/{ip}` — per-attacker drill-down. Per-signal
    breakdown cards (5 metrics) + most-targeted endpoint/signature panel +
    chronological event timeline merging WAF and Bot events with action
    badges, classifier (signature/category), HTTP method, response code.
  - `/alerts` — alert inbox. 4 summary stats (open / critical / acknowledged
    / resolved) + status & severity filters + alert rows with inline ack/
    resolve/reopen action buttons. Status pill + severity pill on each row.
  - `/alerts/{id}` — alert detail. Full description + context dict (with
    source_ip auto-linked to attacker drill-down) + lifecycle timestamps +
    occurrence counter + ack/resolve/reopen buttons.
  - `GeoChoropleth` component — country-level bar list with emoji flags +
    ISO names. Built-in country code → name map for ~40 most common
    countries. Bar list chosen over true choropleth to avoid 80kb TopoJSON
    dependency for the typical 10–30 country dataset.
  - `AlertSeverityBadge` + `AlertStatusBadge` components — color-coded
    pills (severity: critical=red, warning=amber, info=cyan; status:
    open=red, acknowledged=amber, resolved=green).
  - **Sidebar `Alerts` top-nav item** with live count badge — pulls from
    `/alerts/summary` every 30s. Badge color: red if any critical open,
    amber otherwise. Caps display at 99+.
  - **Sidebar Analytics → Security sub-item** (4th in group, after WAF/Bot/API).
  - **Security hero card** on the Overview page — placed after the API
    hero card. 4 stats (active attackers / top country / open alerts /
    critical alerts) + activity strip (24h WAF blocks, bot interventions,
    countries seen). Two action links (Alerts + View analytics).

- **New configuration knobs**:
  - `SECURITY_PROFILE_WINDOW_MINUTES` (default 1440 = 24h)
  - `SECURITY_MAX_ATTACKERS_PER_CYCLE` (default 2000) — circuit breaker
  - `SECURITY_TOPK_SIZE` (default 12)
  - `ALERT_RETENTION_DAYS` (default 90)
  - `ALERT_WAF_BLOCK_BURST_THRESHOLD` (default 50)
  - `ALERT_BOT_CRED_STUFF_MIN_EVENTS` (default 20)
  - `ALERT_BOT_CRED_STUFF_FAILURE_PCT` (default 50.0)
  - `ALERT_API_SHADOW_EMERGENCE_SAMPLES` (default 100)
  - Per-rule on/off flags (all default true): `ALERT_RULE_WAF_BURST_ENABLED`,
    `ALERT_RULE_WAF_NEW_ATTACKER_ENABLED`, `ALERT_RULE_BOT_CRED_STUFF_ENABLED`,
    `ALERT_RULE_API_STATE_CHANGE_ENABLED`, `ALERT_RULE_API_SHADOW_ENABLED`,
    `ALERT_RULE_CERT_EXPIRY_ENABLED`

### Changed

- `seed.py` runs slice 7 tasks last — `refresh_attacker_profiles` and
  `evaluate_alert_rules` only after the event feeds (waf_events,
  bot_events) have populated.
- `/sync/all` includes slice 7 tasks in correct dependency order.
- `/sync/attacker-profiles` and `/sync/alerts/evaluate` added as manual
  triggers for ad-hoc operator testing.

### Deferred (not in slice 7)

- **Slack alerting** — option B in slice 7 question 5, deferred per user
  decision (option A). The rule engine and alerts table are channel-agnostic,
  so adding a Slack delivery hook is ~30 lines if needed later.
- **Schema drift detection** — option B in slice 7 question 4, deferred
  per user decision (option A). Slice 6's `query_params`, `body_params`,
  and `response_codes` capture the data needed; a future slice can add
  declared-vs-observed diff logic.
- **Risk scoring** — option C in question 3. The attacker profile already
  has the underlying signal counts, so a weighted composite is a UI-only
  add later.
- **State transition history** for ML discovery — would require a separate
  history table; current model is point-in-time per cycle.

### Test counts

- Backend: 96/96 passing (was 83, +13 new). New tests cover
  `AttackerAggregates` math, `AttackerKey` shape, alert candidate construction,
  rule registration with on/off flags, and default settings sanity. DB-dependent
  integration tests (correlator + rule eval against real events) require Postgres
  and run in the deployed environment, not in CI sandbox — same pattern as
  prior slices.
- Frontend: Next.js compiles all four slice 7 routes successfully.

### Known limits

- API 4xx attribution per attacker is approximated from WAF events (no
  source_ip on `api_metrics_1min`).
- The `bot.cred_stuffing` rule uses Bot event `challenge_result` field — if
  the F5 XC tenant doesn't have BD-A enabled, this rule sees zero data and
  silently never fires (not an error).
- The "new attacker" detection compares last 1h to a fixed 24h prior window;
  attackers active continuously over multi-day spans don't re-trigger this rule.
- Alert dedup is per-rule, not cross-rule. The same IP can fire
  `bot.cred_stuffing` and `waf.new_attacker` independently — by design,
  since they represent different signal patterns.
- Country-level "choropleth" is rendered as a horizontal bar list rather
  than a true world map — see `GeoChoropleth.tsx` rationale comment.
- No tenant-level rate-limiting on alert generation. A noisy ruleset
  could insert hundreds of new dedupe keys per cycle. Practical mitigation
  is per-rule disable flags.

### Migration notes

**v0.6.0 → v0.7.0 in-place upgrade**:

```bash
cp f5xc-dashboard/.env ~/f5xc-dashboard.env.backup
docker compose -f f5xc-dashboard/docker-compose.yml down
mv f5xc-dashboard f5xc-dashboard.v060.bak
unzip ~/f5xc-dashboard-v0.7.0.zip
cp ~/f5xc-dashboard.env.backup ~/f5xc-dashboard/.env
cd ~/f5xc-dashboard
docker compose up -d --build
```

Alembic auto-applies migration `0006_slice7_security`. Backend log line:
`alembic_at_revision  revision=0006_slice7_security`.

After restart, hit "Sync now" or POST `/api/v1/sync/all`. Slice 7 tasks
run last so they see the freshly-populated event tables. First view of
`/analytics/security` should show populated attacker profiles (mock data
generates ~5–10 cross-signal attackers spanning 6 countries).

---

## v0.6.0 — Slice 6 (2026-04-29)

API statistics + ML discovery state. Surfaces F5 XC's ML-discovered API
inventory alongside declared OpenAPI specs, with per-endpoint time-series
(volume + p50/p95/p99 latency) and shadow-endpoint detection — endpoints
the ML model found that were never declared in any api_definition.

### Added

- **Three new sync sources**:
  - `sync_api_endpoints` (every `POLL_CONFIG_INTERVAL`, default 10 min):
    pulls discovered endpoint inventory per LB. Joins each (method, path)
    against declared endpoints from attached api_definitions to populate
    the `is_shadow` flag.
  - `sync_api_discovery_state` (every `POLL_CONFIG_INTERVAL`):
    pulls ML lifecycle state per LB — learning / mature / enforcing /
    disabled — with confidence score, endpoint count, traffic samples.
  - `sync_api_metrics` (every `POLL_ANALYTICS_INTERVAL`, default 5 min):
    per-endpoint time-series at 60s step. Captures request count, 4xx, 5xx,
    p50, p95, p99 latency. Heaviest sync in the system on busy tenants.

- **Four new tables** with retention policies:
  - `api_endpoints` — standard table (bounded cardinality). Holds discovered
    endpoint inventory with full taxonomy: method, path, is_shadow, auth_type,
    discovery_confidence, response codes, query_params, body_params,
    sample counts, first/last seen.
  - `api_discovery_states` — one row per LB. ML lifecycle state.
  - `api_metrics_1min` — TimescaleDB hypertable. Per (bucket, lb, method,
    endpoint) tuple. Retention 30d.
  - `api_metrics_1hour` — continuous aggregate. Aggregation semantics:
    SUM for counts, AVG for p50, MAX for p95/p99 (worst-case-in-hour
    latency, since percentiles can't be averaged correctly across buckets).
    Retention 90d.

- **Schema extension**: added `declared_endpoints` JSONB column to existing
  `api_definitions` table. The slice 3 transformer now extracts the flat
  list of (method, path) tuples from OpenAPI/Swagger spec paths{} — used
  for shadow-endpoint detection.

- **API endpoints** under `/api/v1/analytics/api`:
  - `GET /overview` — tenant rollup: total_endpoints, shadow_endpoints,
    declared_endpoints, state_counts dict, avg_p99_latency_ms, error_rate_pct
  - `GET /discovery-state` — per-LB ML state list
  - `GET /endpoints` — paginated endpoint inventory with shadow_only filter,
    sort options (volume / last_seen / method / path), LB and auth_type filters
  - `GET /endpoints/{id}` — single endpoint detail with full inferred shape
  - `GET /endpoints/{id}/sparkline` — 24h @ 5-min metrics for one endpoint
  - `GET /topk?dim=...` — 6 top-K dimensions: volume, latency_p99,
    error_rate (per-mille), shadow (top shadow endpoints by traffic),
    method, auth_type

- **New routes / UI components**:
  - `/analytics/api` — main dashboard. 4 hero stats (total / shadow /
    avg p99 / error rate) + per-LB ML state table with state badges +
    6 top-K cards + endpoint inventory table (method+path, LB, status pill
    Shadow/Declared, auth type, confidence, samples, response codes,
    last seen). Filter: shadow-only checkbox. Sort: volume / last_seen /
    method / path.
  - `/analytics/api/endpoints/{id}` — per-endpoint detail page with full
    sparkline (req volume + p50 dashed + p99 solid), discovery metadata
    panel, inferred shape panel (query + body params with name/type/required).
  - `DiscoveryStateBadge` component — color-coded state pills:
    enforcing=green, mature=cyan, learning=amber, disabled/unknown=gray.
  - `ApiEndpointSparkline` component — twin-axis chart (left: req/min,
    right: ms latency).
  - **API hero card** on the Overview page — counts + state distribution
    summary, placed after the Bot hero card.
  - **Per-LB API discovery card** on LB detail page — endpoint count,
    shadow count, ML state badge, traffic samples. Always shown if any
    discovery data exists.
  - Sidebar Analytics → API sub-item.

- **New configuration knobs**:
  - `API_METRICS_WINDOW_MINUTES` (default 10)
  - `API_MAX_ENDPOINTS_PER_CYCLE` (default 2000) — circuit breaker per LB
  - `API_TOPK_SIZE` (default 12)

### Changed

- `seed.py` now also runs `sync_api_discovery_state`, `sync_api_endpoints`,
  `sync_api_metrics` on first boot. Order matters: `sync_policies` must
  run before `sync_api_endpoints` so api_definitions exist (their
  declared_endpoints field is what shadow detection compares against).
- `/sync/all` adds the three new tasks in correct dependency order.
- F5XCClient gains `list_api_endpoints()`, `get_api_discovery_state()`,
  `get_api_endpoint_metrics()`. The metrics endpoint reuses
  `metrics_multi_v2` URL but with a `group_by: ["method", "endpoint"]`
  body parameter — the mock client now routes by body content to keep
  WAF/bot fixtures separate from API fixtures.
- Mock fixture for `shared_api_definitions.json` now declares 8 paths in
  `public-api-v2-spec` (matching api-prod-lb's non-shadow endpoints) and
  adds a new `ecommerce-checkout-api` definition with 3 declared paths
  (intentionally narrow — the rest of www-prod-lb's API surface is shadow).
- LB fixtures gain `api_definition.api_definitions[]` references so
  `sync_policies` produces correct PolicyAttachment rows for shadow
  detection in `sync_api_endpoints`.

### Decisions locked from slice 6 question round

| Question | Answer | Notes |
|---|---|---|
| 1. Discovery scope | B — api_definition + per-LB inferred endpoints | Shadow detection is the operational value |
| 2. ML state | B — state + confidence + counts | Beyond state-only is "alerting" territory (slice 7) |
| 3. Per-endpoint detail | B — method+path + count + last seen + params + response codes | PII/schema-match deferred to slice 7 |
| 4. Time-series | B — api_metrics_1min hypertable with latency percentiles | Per-event sampling too expensive |
| 5. Top-K dims | 6 widgets: volume / latency_p99 / error_rate / shadow / method / auth_type | Same cardinality as slice 4/5 |

### Mock data scenarios

The fixtures simulate three realistic scenarios:

1. **api-prod-lb — mature/enforcing** (`public-api-v2-spec` declared, full coverage):
   15 endpoints, 12 declared, 3 shadow. State: `enforcing`, confidence 96%,
   245k traffic samples. Shadow endpoints intentionally suspicious:
   `/api/v2/internal/debug` (bearer), `/api/v2/admin/flush-cache` (apikey),
   `/api/v2/legacy/customer-data` (no auth!).
2. **www-prod-lb — mature, partial coverage** (`ecommerce-checkout-api`
   declares only 3 paths): 15 endpoints, 3 declared, 12 shadow. State:
   `mature`, confidence 87%, 132k samples. Shadow endpoints are real
   ecommerce paths nobody documented: `/api/recommendations`, `/api/wishlist`,
   `/api/coupons/apply`, `/api/profile`, `/api/orders/history`, etc.
3. **legacy-internal-http — learning** (no api_definition attached):
   2 endpoints, both shadow. State: `learning`, confidence 42%, 279 samples.
   Demonstrates the "low-traffic LB still in learning state" case.

Per-endpoint metrics fixtures generate 24h @ 5-min for the top 8 endpoints
on each LB. Latency curves show realistic load-correlated degradation
(p99 climbs ~50% during peak hour). Error rates are auth-type aware:
authenticated endpoints have ~5% 4xx (mostly 401s), public have ~1%.

### Test counts

- Backend: 83/83 passing (was 62, +21 new). New tests cover auth-type
  normalization, discovery state aliasing, declared endpoint extraction
  from OpenAPI specs, shadow vs declared classification, per-endpoint
  metric grouping with crosstalk verification (API metrics calls don't
  pollute WAF/bot metrics fixtures and vice versa).

### Migration notes

**v0.5.0 → v0.6.0 in-place upgrade**:

```bash
cp f5xc-dashboard/.env ~/f5xc-dashboard.env.backup
docker compose -f f5xc-dashboard/docker-compose.yml down
mv f5xc-dashboard f5xc-dashboard.v050.bak
unzip ~/f5xc-dashboard-v0.6.0.zip
cp ~/f5xc-dashboard.env.backup ~/f5xc-dashboard/.env
cd ~/f5xc-dashboard
docker compose up -d --build
```

Alembic auto-applies migration `0005_slice6_api`. Watch for
`alembic_at_revision  revision=0005_slice6_api` in backend logs. After
restart, hit "Sync now" — the dependency-ordered run will populate
api_definitions (with new declared_endpoints column), then
api_endpoints (with shadow flags computed against declared_endpoints).

For live mode (`F5XC_MOCK=false`): the per-endpoint metrics sync can
generate substantial DB traffic on busy tenants. An LB with 500 endpoints
× 10 minute window = 5000 rows per cycle per LB. If you see
`api_endpoints_circuit_breaker_hit` warnings, increase
`API_MAX_ENDPOINTS_PER_CYCLE` from 2000.

### Known limits

- The discovery state lifecycle is point-in-time per cycle. Slice 6
  doesn't track state transition history (e.g., "API X has been in
  learning for 14 days" alerts) — that's slice 7 territory.
- Schema validation (declared OpenAPI vs observed traffic) is not
  computed. The endpoint detail page shows declared vs shadow but doesn't
  flag when an endpoint has drifted from its declared spec. Slice 7.
- F5 XC ML can occasionally produce duplicate endpoints with parameter
  variations (e.g., `/users/{id}` and `/users/123`). Our shadow detection
  treats path-pattern matching strictly — `/users/123` won't match
  `/users/{id}` declared. Live tenants may see more "shadow" entries than
  expected if their api_definition uses `{id}` patterns but ML observed
  concrete IDs. This is a known F5 XC quirk.
- The continuous aggregate uses MAX(p99) not actual p99-of-p99s. This
  gives "worst case latency in the hour" which is what operators usually
  want, but it's not statistically a true p99 across the hour's request
  population.

---

## v0.5.0 — Slice 5 (2026-04-29)

Bot statistics — dual-source ingestion (BD Standard via security_events +
BD-A via bot_traffic), full taxonomy, per-endpoint breakdown view.

(Abridged.)

- Three hypertables: `bot_events`, `bot_metrics_1min`, `bot_metrics_1hour`
- Sync tasks: `sync_bot_events`, `sync_bot_metrics`
- API: `/analytics/bot/{overview,sparkline,topk,events,endpoints}`
- Frontend: `/analytics/bot` page, `/analytics/bot/endpoints`, hero cards, per-LB cards
- 62/62 tests

---

## v0.4.0 — Slice 4 (2026-04-28)

WAF analytics — first time-series feature. Hypertable-backed metrics and
events, sparklines, top-K dashboards, recent events drill-down.

- 46/46 tests

---

## v0.3.0 — Slice 3 (2026-04-27)

Policy visibility (WAF, service policy, bot defense, API definition) +
Alembic migrations.

- 36/36 tests

---

## v0.2.0 — Slice 2 (2026-04-27)

Per-origin per-site healthcheck visibility, origin pool drill-down, LB detail page.

---

## v0.1.1 — hotfix (2026-04-24)

- Fixed frontend proxy: runtime `API_BASE_URL` env
- Fixed missing `frontend/public/.gitkeep`
- Disabled inherited HTTP healthcheck on worker/beat
- Added `make reset-admin-password`

## v0.1.0 — initial release

Slice 0 (foundation) + Slice 1 (LB inventory + cert expiration).
