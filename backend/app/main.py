"""FastAPI application entrypoint — v0.7.2 hardened.

Wiring (top to bottom):
  1. Lifespan: configure_logging, run_migrations, validate_production_safe.
     Refuses to boot in live mode (F5XC_MOCK=false) if secrets/config are
     unsafe; warn-only in mock mode.
  2. SlowAPIMiddleware + 429 handler. The Limiter instance is owned by
     app.api.auth (route-level decorator on /login).
  3. SecurityHeadersMiddleware (HSTS conditional on TLS, nosniff, frame-deny,
     CSP for JSON API responses).
  4. CORS — scoped via settings.cors_origins_list. Same-origin via Next.js
     rewrites means cors_origins_list is empty and no CORS middleware is
     installed; explicit origins only when SPA is on a different host.
  5. F5XCError handler — sanitizes upstream response bodies.
  6. /healthz at root (unchanged from v0.7.1).
  7. Mounts api_router (which carries the /api/v1 prefix and all sub-routers).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app import __version__
from app.api import api_router
from app.api.auth import limiter as auth_limiter
from app.config import get_settings
from app.db import engine
from app.f5xc.client import F5XCError
from app.logging_config import configure_logging, get_logger
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.migrations import run_migrations

configure_logging()
log = get_logger(__name__)
settings = get_settings()



async def _probe_f5xc_auth() -> None:
    """v0.8.0 startup probe: confirm the configured F5 XC token authenticates.

    Warn-only — never blocks startup. If the probe fails (bad token, network
    issue, F5 XC outage) the dashboard still starts; sync tasks will surface
    the failure when they fire. Local features (UI, audit log, cached
    inventory) work regardless. Skipped in mock mode.
    """
    from app.f5xc.client import get_f5xc_client  # local to keep import surface small

    try:
        client = await asyncio.to_thread(get_f5xc_client)
        try:
            # list_sites maps to /api/config/namespaces/system/sites — the lightest
            # authenticated call. Returns regardless of namespace contents.
            sites = await asyncio.to_thread(client.list_sites)
            log.info(
                "f5xc_auth_probe_ok",
                tenant=settings.f5xc_tenant,
                sites_visible=len(sites),
            )
        finally:
            await asyncio.to_thread(client.close)
    except F5XCError as e:
        log.warning(
            "f5xc_auth_probe_failed",
            tenant=settings.f5xc_tenant,
            namespace=settings.f5xc_namespace,
            status_code=e.status_code,
            error=str(e)[:200],
            note="dashboard will start; sync tasks may fail until token is corrected",
        )
    except Exception as e:  # noqa: BLE001
        log.warning(
            "f5xc_auth_probe_error",
            tenant=settings.f5xc_tenant,
            error_type=type(e).__name__,
            error=str(e)[:200],
            note="dashboard will start; sync tasks may fail until F5 XC is reachable",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    # Alembic-backed migrations. Stamps existing v0.2.0 deployments to baseline
    # automatically; upgrades fresh DBs from scratch.
    run_migrations(engine)

    # Production safety check.
    problems = settings.validate_production_safe()
    if problems:
        for p in problems:
            log.error("production_config_violation", problem=p)
        if not settings.f5xc_mock:
            log.critical(
                "refusing_to_start",
                reason="production_config_violations",
                count=len(problems),
            )
            raise SystemExit(2)
        else:
            log.warning(
                "mock_mode_running_with_violations",
                count=len(problems),
                note="violations would block startup in live mode",
            )

    # v0.8.0 — startup auth probe (warn-only, hard-bounded at 5s). Catches
    # tokens that are syntactically present but semantically wrong (expired,
    # revoked, etc.) which validate_production_safe cannot detect. The 5s
    # bound prevents a slow F5 XC, retry-storm, or hung connection from
    # blocking lifespan startup; sync tasks have their own retry budget and
    # will surface persistent failures.
    if not settings.f5xc_mock:
        try:
            await asyncio.wait_for(_probe_f5xc_auth(), timeout=5.0)
        except asyncio.TimeoutError:
            log.warning(
                "f5xc_auth_probe_timeout",
                tenant=settings.f5xc_tenant,
                timeout_seconds=5,
                note="dashboard will start; sync tasks will surface persistent F5 XC failures",
            )

    log.info(
        "f5xc_dashboard_startup",
        mock=settings.f5xc_mock,
        tenant=settings.f5xc_tenant,
        cors_origins=settings.cors_origins_list,
        cookie_secure=settings.session_cookie_secure,
        login_rate_limit=settings.auth_login_rate_limit,
    )
    yield
    log.info("f5xc_dashboard_shutdown")


app = FastAPI(
    title="F5 XC Dashboard",
    version=__version__,
    description="Read-only visibility over F5 Distributed Cloud config + analytics.",
    lifespan=lifespan,
)

# ---- Rate limiting (slowapi) -----------------------------------------------
# Order: register limiter on app.state BEFORE adding SlowAPIMiddleware.
# The decorator on /login (in app.api.auth) does the actual enforcement;
# this wires up the structured 429 response.
app.state.limiter = auth_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ---- Security headers ------------------------------------------------------
app.add_middleware(SecurityHeadersMiddleware)

# ---- CORS ------------------------------------------------------------------
# Same-origin via Next.js rewrites → cors_origins_list is empty → no CORS
# middleware. Only install when SPA runs on a different origin and needs
# preflight. allow_credentials=True is REQUIRED for cookie auth; browsers
# reject wildcard origins when credentials=true, hence the explicit list.
_cors_origins = settings.cors_origins_list
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

# ---- Upstream error sanitization -------------------------------------------
@app.exception_handler(F5XCError)
async def _f5xc_error_handler(request: Request, exc: F5XCError):  # noqa: ARG001
    # Full detail server-side; generic 502 to client. Don't leak F5 XC
    # response bodies (which may include tenant/namespace identifiers,
    # internal URLs, or rate-limit headers).
    log.error(
        "f5xc_upstream_error",
        path=request.url.path,
        status=getattr(exc, "status", None),
        error=type(exc).__name__,
        detail=str(exc),
    )
    return JSONResponse(
        status_code=502,
        content={
            "detail": "Upstream F5 XC API error",
            "status": getattr(exc, "status", None),
        },
    )


# ---- Routes ----------------------------------------------------------------
app.include_router(api_router)


@app.get("/healthz", include_in_schema=False)
def root_healthz() -> dict:
    return {"status": "ok", "version": __version__}
