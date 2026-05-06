# Architecture

## Component diagram

```
           ┌──────────────────────────────────────────────────────────────┐
           │                    USER BROWSER                              │
           │   Next.js 15 App Router · TanStack Query · Tailwind · Recharts │
           └───────────────────────┬──────────────────────────────────────┘
                                   │  HTTPS / Bearer JWT
                                   ▼
           ┌──────────────────────────────────────────────────────────────┐
           │                  FASTAPI BACKEND (uvicorn)                   │
           │  /api/v1/auth   /loadbalancers   /certificates   /sync       │
           │  ─ Local+OIDC auth providers  ─ RBAC (admin, viewer)         │
           └──┬────────────────────┬────────────────────┬─────────────────┘
              │                    │                    │
              ▼                    ▼                    ▼
    ┌──────────────────┐ ┌──────────────────┐  ┌─────────────────────────┐
    │   POSTGRES 16    │ │      REDIS       │  │    F5XCClient (httpx)   │
    │ + TimescaleDB    │ │  broker + cache  │  │  + tenacity retry       │
    │  config snapshots│ │                  │  │  + MOCK mode (fixtures) │
    │  users, tenants  │ └────────┬─────────┘  └────────────┬────────────┘
    └──────────────────┘          │                         │
              ▲                    │                         │ APIToken <t>
              │                    │                         ▼
              │             ┌──────┴───────────┐   ┌──────────────────────┐
              │             │  CELERY WORKERS  │──▶│   F5 XC Console      │
              │             │  sync tasks      │   │   *.console.ves.io   │
              └─────────────┤  (upsert on key) │   │   REST API           │
                            └──────────▲───────┘   └──────────────────────┘
                                       │
                              ┌────────┴─────────┐
                              │   CELERY BEAT    │
                              │   periodic jobs  │
                              └──────────────────┘
```

## Data flow — one polling cycle

1. **Beat** triggers `sync_loadbalancers` every `POLL_CONFIG_INTERVAL` (default 600s).
2. **Worker** picks up task, iterates all `Tenant` rows (v1: one).
3. For each tenant, `F5XCClient.list_http_load_balancers()` returns `items[]` from `/api/config/namespaces/{ns}/http_loadbalancers`.
4. `extract_lb_fields()` flattens each item: domains, LB type (http/https), advertise mode, policy attachment flags (WAF, service policy, bot, API protection), origin pool refs, cert ref, raw spec.
5. INSERT…ON CONFLICT DO UPDATE on `(tenant_id, namespace, name)` — the table holds the **current state**; mutation history is additive and deferred to a slice 2+ snapshot table.
6. `last_seen_at` bumped. Rows not seen in a poll are **not** deleted in v1 — stale rows stand out visually via "last seen" age. Deletion reconciliation is a v0.2 feature (avoid race with mid-sync failures).

Same pattern for `sync_certificates` and `sync_origin_pools`.

## Certificate parsing

Cert expiry comes from two possible sources depending on issuance mode:

| Mode | Source of truth | Notes |
|---|---|---|
| Manual upload | `spec.certificate_url` → `string:///<base64-PEM>` → parse with `cryptography.x509` | Full subject / issuer / SANs / serial / fingerprint available |
| F5 auto-cert | `spec.auto_cert_info.auto_cert_expiry` (ISO-8601) + `auto_cert_subject_name` | Less detail; parsed ISO string |

`extract_cert_fields()` tries the PEM path first, falls back to `auto_cert_info`. `classify_cert_status()` applies the thresholds (`CERT_WARN_DAYS`, `CERT_CRITICAL_DAYS`) and returns one of `ok | warn | critical | expired | unknown`.

## F5 XC quirks accounted for

- **Object model** is `{metadata, spec}` for writes, `{metadata, get_spec, system_metadata}` for reads. Transformers look at both `get_spec` and `spec` to be tolerant.
- **Advertise mode** is a protobuf oneof: `advertise_on_public_default_vip`, `advertise_on_public`, `advertise_custom`, `do_not_advertise`. Transformer records which key is present.
- **LB type** is another oneof: `http`, `https`, `https_auto_cert`. Mapped to `http` / `https` for the UI.
- **Collection name** is `kind + "s"` even when grammatically wrong (`service_policys`). Reflected in planned slice 3 endpoints.
- **Namespace `shared`** is where tenant-wide objects live (WAF policies often live here — transformer captures the FQN ref, not just local-namespace names).
- **63-character object name limit** — not enforced here (read-only), but noted for a future create/edit feature slice.

## Retry + rate limiting

`F5XCClient` wraps each HTTP call in tenacity with exponential backoff (1s → 30s cap) on:
- `httpx.TransportError` (network failures)
- HTTP 429, 5xx (via a custom `F5XCError` raise inside the wrapped call)

4xx other than 429 are **not retried** — these are config errors (bad token, 404, 403) where retrying would just waste calls.

## Why TimescaleDB

Slices 4–7 introduce time-series analytics (WAF events/min, bot signal rollups, API endpoint request rates). TimescaleDB hypertables + continuous aggregates handle 90d raw + 13mo rollups cleanly. The extension is already enabled in `infra/init-db.sql` even though no hypertables exist yet in v1 — that way slice 4's migration is "create hypertable" only.

## Auth architecture

```
AuthProvider (ABC)
├── LocalAuthProvider       ← active in v1; bcrypt + JWT
└── OIDCAuthProvider        ← stub; see docs/OIDC.md for wire-up plan
```

Provider is resolved at request time via `get_auth_provider()` reading `AUTH_PROVIDER` env var. Switching to OIDC is a config change — no code refactor needed once the stub is implemented.

`get_current_user` dependency decodes JWT, loads User by UUID, enforces `is_active`. `require_admin` is a layered dep for write-capable endpoints (currently just `/sync/*`).

## Multi-tenant future-proofing

Every domain table has `tenant_id UUID FK → tenants(id) ON DELETE CASCADE`. All API queries filter on `user.tenant_id`. Seeding one tenant in v1 costs nothing; supporting N in v0.3 is a registration flow + per-tenant token storage change.

## Deferred until future slices

- Healthcheck status polling (requires `/api/data/namespaces/.../health` fan-out per pool)
- Time-series analytics schema (hypertables for WAF/Bot/API/Security events)
- Change-detection / diff view (snapshot table `load_balancer_snapshots` keyed by `(lb_id, hash)`)
- Alerting (cert expiry email/Slack)
- RBAC scoped to namespace (current: tenant-wide viewer/admin)
- Write operations (config changes from dashboard) — explicitly out of scope per v1 requirements
