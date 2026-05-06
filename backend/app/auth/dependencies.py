"""FastAPI dependencies for cookie-based auth + CSRF.

Auth model
----------
- Access token lives in a httpOnly + SameSite=Strict + Secure cookie
  (`f5xc_session`). XSS cannot read it; CSRF cannot misuse it cross-origin
  thanks to SameSite.
- Refresh token in another httpOnly cookie (`f5xc_refresh`), only sent
  to /api/v1/auth/refresh path.
- CSRF token in a non-httpOnly cookie (`f5xc_csrf`). The SPA reads it on
  boot and echoes back in `X-CSRF-Token` header on every mutating request.
  Server validates the header equals the cookie (double-submit).

The CSRF check is required for POST/PUT/PATCH/DELETE. GET/HEAD/OPTIONS
are read-only and do not require CSRF (per OWASP).
"""
from __future__ import annotations

import uuid

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.revocation import is_revoked
from app.auth.security import constant_time_compare, decode_access_token
from app.config import get_settings
from app.db import get_db
from app.models import User


def _settings():
    return get_settings()


def get_session_token(request: Request) -> str | None:
    """Extract the access JWT from the session cookie."""
    return request.cookies.get(_settings().session_cookie_name)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Resolve the user from the session cookie. 401 on any failure."""
    token = get_session_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed session"
        ) from e
    # v0.8.0 — revocation check. Tokens issued before this code shipped
    # lack `jti`; we treat that as "skip check" so existing sessions don't
    # break on deploy. Redis-unreachable is fail-closed (returns 401)
    # because the dashboard depends on Redis for rate-limit + queues
    # anyway; bypassing auth on Redis outage would be the wrong default.
    jti = payload.get("jti")
    if jti is not None:
        try:
            if is_revoked(jti):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session revoked",
                )
        except HTTPException:
            raise
        except Exception as e:  # redis.RedisError or anything else
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Auth backend unavailable",
            ) from e
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required"
        )
    return user


# CSRF — double-submit token check. Required on mutating methods.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def csrf_protect(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> None:
    """Enforce double-submit CSRF check on mutating requests.

    Use as `dependencies=[Depends(csrf_protect)]` on routers that include
    POST/PUT/PATCH/DELETE endpoints. Safe methods (GET/HEAD/OPTIONS) are
    let through without check.
    """
    if request.method in _SAFE_METHODS:
        return
    settings = _settings()
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    if not cookie_token or not x_csrf_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing"
        )
    if not constant_time_compare(cookie_token, x_csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token mismatch"
        )


def get_csrf_cookie(
    csrf_cookie: str | None = Cookie(default=None, alias="f5xc_csrf"),
) -> str | None:
    """Convenience for endpoints that want to read the CSRF cookie value
    (typically only the /auth/me boot endpoint, to confirm to the client
    that a CSRF token is established)."""
    return csrf_cookie
