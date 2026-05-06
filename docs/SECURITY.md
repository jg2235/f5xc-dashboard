# Security Posture — F5 Distributed Cloud Dashboard

Last reviewed: v0.7.2 (2026-05-01)

## Threat model

The dashboard is an internal-facing tool that holds an F5 XC API token
with broad read access to a tenant. Realistic threats and mitigations:

| Threat | Mitigation |
|---|---|
| Stolen JWT in browser localStorage (XSS) | Tokens are in httpOnly cookies; JS cannot read them |
| CSRF on state-changing endpoints | SameSite=Strict cookies + double-submit CSRF token (`X-CSRF-Token` header echoed from `f5xc_csrf` cookie) |
| Session hijack via plaintext channel | TLS-only via Caddy. Cookies marked `Secure`. HSTS emitted when on TLS |
| Brute-force login | slowapi rate limit (`AUTH_LOGIN_RATE_LIMIT`, default 5/15min per IP). Failed attempts audit-logged |
| Credentials in environment / process listing | `JWT_SECRET_KEY`, `F5XC_API_TOKEN`, `POSTGRES_PASSWORD` live only in `/run/secrets/*`. The backend reads them at startup; they do not appear in `docker inspect` env or `env` listings inside the container |
| Container compromise → host root | Postgres, Redis, Caddy run as non-root by default. Backend currently runs as root (deferred to v0.8.0) |
| Iframe / clickjacking on the SPA | `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` |
| MIME sniffing → script injection | `X-Content-Type-Options: nosniff` |
| Data exfil via referrer | `Referrer-Policy: strict-origin-when-cross-origin` |
| Browser-API surface (camera, geo, etc.) | `Permissions-Policy` denies all by default |
| Information disclosure via upstream errors | F5 XC API error bodies are not echoed to HTTP clients; the response is generic 502 + audit-logged detail server-side |
| Persistent record of attacker activity | `audit_events` table records login success/failure, logout, refresh, with IP + user-agent. Retention 180 days, enforced by daily celery beat task `audit.cleanup_audit_events` |

## What is NOT yet mitigated (v0.7.2)

- **No JWT revocation list.** Refresh-token rotation issues a new `jti` on every
  refresh, but compromised access tokens remain valid until natural expiry
  (60 min default). Reduce blast radius by lowering
  `JWT_ACCESS_TOKEN_EXPIRES_MINUTES`. Full revocation deferred to v0.8.0.
- **Backend container runs as root.** Postgres, Redis, Caddy run as non-root
  by image default. Backend Dockerfile rewrite to UID 10001 deferred to v0.8.0.
- **No upstream auth probe.** A misconfigured `F5XC_API_TOKEN` is detected
  only on the first sync. Roadmap: warn at startup if a `/api/web/whoami`
  probe fails, without blocking boot.
- **No anomaly detection on audit events.** The table exists; no alerting
  on it yet.
- **CSP for the SPA is not set here.** This document covers the API and
  reverse proxy. The frontend (Next.js) has its own CSP responsibility;
  `SecurityHeadersMiddleware` deliberately leaves HTML responses alone
  so the SPA can set a tighter policy.
- **OIDC provider is configured but not wired.** Auth provider abstraction
  lives at `app/auth/providers.py`; only `local` is currently active.
- **Secrets directory + bak files** can leak sensitive material if checked
  in to git. The repo `.gitignore` excludes `secrets/*` and the in-directory
  `secrets/.gitignore` is belt-and-braces. `*.bak` and `*.v071.bak` files
  from the v0.7.2 apply contain pre-rotation values; clean them up via
  `make clean-bak`.

## Operational notes

### Cookie scope

- Session and CSRF cookies scoped to `/`. Refresh cookie scoped to
  `/api/v1/auth` so it is sent only to the refresh endpoint.

### Same-site vs cross-origin

- When SPA and API share a hostname (Caddy reverse-proxying both),
  `CORS_ALLOW_ORIGINS` should be empty. Browsers treat the requests as
  same-origin and skip the preflight entirely.
- If you serve the SPA from a different origin than the API, set
  `CORS_ALLOW_ORIGINS` to an explicit list and expect OPTIONS preflight
  on every mutating request. `allow_credentials=true` is required and
  means wildcard origins are rejected by browsers.

### Rotating secretsTo rotate the postgres password, see the `make` target backlog (deferred);
manual procedure is `ALTER USER f5xc WITH PASSWORD '...'` in postgres,
then update `secrets/postgres_password`, then restart backend stack.

### Production checklist

Before exposing publicly:

- [ ] `F5XC_MOCK=false`
- [ ] `SESSION_COOKIE_SECURE=true` (default)
- [ ] `SESSION_COOKIE_SAMESITE=strict` (or `lax` only if you have a
      legitimate cross-site GET that needs a session — rare)
- [ ] `JWT_SECRET_KEY` length ≥ 32 chars (validator checks this)
- [ ] Caddyfile `localhost` block replaced with public hostname; `tls
      internal` swapped for `tls ops@example.com` (ACME)
- [ ] DNS A/AAAA points to deployment host
- [ ] Cloud firewall: 80/443 only
- [ ] Backup `secrets/` directory to a secret manager (Vault, AWS Secrets
      Manager, etc.); the on-disk copy in `secrets/` is dev-only
- [ ] Confirm `validate_production_safe()` returns 0 violations after
      lifespan startup

## Reporting

Internal tool. File an issue in the project tracker. Mark sensitive
findings as restricted-visibility.
