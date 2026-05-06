"""Security response headers.

Applied as ASGI middleware. Behaviour:

- Strict-Transport-Security: only emitted when the request was received
  over TLS (either direct https or X-Forwarded-Proto: https from a
  trusted reverse proxy like Caddy). HSTS over plain HTTP is meaningless
  and HSTS over a misconfigured proxy can lock users out.
- X-Content-Type-Options: nosniff (always)
- X-Frame-Options: DENY (always — no framing of API or app)
- Referrer-Policy: strict-origin-when-cross-origin
- Content-Security-Policy: applied to JSON API responses only. The frontend
  is served by a separate origin/path and should set its own CSP. For
  API responses, default-src 'none' is appropriate; nothing renders these.
- Permissions-Policy: minimal restrictive defaults.

The CSP application is content-type-aware: HTML responses are left
untouched so a downstream service (Next.js, etc.) can set its own.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_HSTS_VALUE = "max-age=31536000; includeSubDomains"
_API_CSP = "default-src 'none'; frame-ancestors 'none'"
_PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), payment=(), usb=()"
)


def _is_tls(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    # Trust X-Forwarded-Proto only when set by the reverse proxy.
    # The proxy is responsible for stripping client-supplied values.
    xfp = request.headers.get("x-forwarded-proto", "").lower()
    return xfp == "https"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        response = await call_next(request)
        h = response.headers

        # Always-on baseline.
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", _PERMISSIONS_POLICY)

        # HSTS only when actually on TLS.
        if _is_tls(request):
            h.setdefault("Strict-Transport-Security", _HSTS_VALUE)

        # CSP for API responses (JSON). Don't override anything already set.
        ctype = h.get("content-type", "").split(";")[0].strip().lower()
        if ctype == "application/json" and "content-security-policy" not in h:
            h["Content-Security-Policy"] = _API_CSP

        return response
