# OIDC activation plan

The `OIDCAuthProvider` is a stub in v1. It raises `NotImplementedError` on any `authenticate()` call. Wiring is ready so activation is config-only once implemented.

## Planned flow

```
Browser → /api/v1/auth/oidc/login
         → 302 to OIDC_ISSUER_URL/authorize?...&redirect_uri=OIDC_REDIRECT_URI
IdP     → user signs in
Browser → OIDC_REDIRECT_URI?code=<...>
Frontend → POST /api/v1/auth/oidc/callback { code }
Backend  → exchange code → tokens via token endpoint
         → GET userinfo
         → upsert User by (issuer, sub) into users table (hashed_password NULL)
         → issue local JWT (same mechanism as local auth)
Frontend → store JWT, redirect to /
```

## Targets validated

- **Okta** — primary target per v1 spec
- **Entra ID (Azure AD)** — same OIDC standard
- **Auth0** / **Google** — drop-in via discovery URL

## Implementation checklist (slice 1.5)

- [ ] Add `authlib` dep (or continue with `python-jose` + manual discovery fetch — `authlib` is cleaner for OIDC code exchange)
- [ ] New endpoints in `app/api/auth.py`: `GET /auth/oidc/login`, `POST /auth/oidc/callback`
- [ ] Implement `OIDCAuthProvider.exchange_code()` and `authenticate_by_userinfo()`
- [ ] Store `(issuer, sub)` on User — add nullable columns, migrate
- [ ] Frontend: `/auth/callback` route that posts code, stores returned JWT
- [ ] Doc: per-provider setup (Okta app registration, Entra app registration)

## Security considerations when enabling

- PKCE required for public clients (even though this is a server-side callback, enable it — low cost, reduces attack surface)
- State parameter validation to prevent CSRF on the callback
- JWT of local origin is preferred over forwarding the IdP's ID token — keeps session-termination authoritative
- Tenant assignment: first-login-per-domain auto-provisions to a mapped tenant (configured via env), or admin-invite-only (more secure; v1 default would be invite-only)
