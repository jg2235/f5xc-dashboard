"""Cookie-set/clear helpers — single source of truth for cookie attributes."""
from __future__ import annotations

from fastapi import Response

from app.config import get_settings


def _cookie_kwargs(secure: bool, samesite: str, domain: str) -> dict:
    kw: dict = {
        "secure": secure,
        "samesite": samesite,
        "path": "/",
    }
    if domain:
        kw["domain"] = domain
    return kw


def set_session_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    """Access token. httpOnly. Sent on every same-site request to /."""
    s = get_settings()
    response.set_cookie(
        key=s.session_cookie_name,
        value=token,
        max_age=max_age_seconds,
        httponly=True,
        **_cookie_kwargs(s.session_cookie_secure, s.session_cookie_samesite, s.session_cookie_domain),
    )


def set_refresh_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    """Refresh token. httpOnly + path scoped to /api/v1/auth.

    Path-scoping limits accidental exposure: only the auth endpoints
    receive this cookie. Login, logout, refresh.
    """
    s = get_settings()
    kw = _cookie_kwargs(s.session_cookie_secure, s.session_cookie_samesite, s.session_cookie_domain)
    kw["path"] = "/api/v1/auth"
    response.set_cookie(
        key=s.refresh_cookie_name,
        value=token,
        max_age=max_age_seconds,
        httponly=True,
        **kw,
    )


def set_csrf_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    """CSRF token. NOT httpOnly — the SPA must read it to echo in headers."""
    s = get_settings()
    response.set_cookie(
        key=s.csrf_cookie_name,
        value=token,
        max_age=max_age_seconds,
        httponly=False,  # SPA must read this in JS
        **_cookie_kwargs(s.session_cookie_secure, s.session_cookie_samesite, s.session_cookie_domain),
    )


def clear_auth_cookies(response: Response) -> None:
    """Clear session, refresh, CSRF cookies. Called on logout."""
    s = get_settings()
    common = _cookie_kwargs(s.session_cookie_secure, s.session_cookie_samesite, s.session_cookie_domain)
    response.delete_cookie(key=s.session_cookie_name, path="/", **{k: v for k, v in common.items() if k != "path"})
    response.delete_cookie(key=s.refresh_cookie_name, path="/api/v1/auth", **{k: v for k, v in common.items() if k != "path"})
    response.delete_cookie(key=s.csrf_cookie_name, path="/", **{k: v for k, v in common.items() if k != "path"})
