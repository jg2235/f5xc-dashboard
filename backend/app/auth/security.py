"""JWT + bcrypt + CSRF helpers for cookie-based auth."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_ctx.verify(plain, hashed)
    except Exception:  # noqa: BLE001
        return False


def _encode(payload: dict[str, Any]) -> str:
    settings = get_settings()
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(
    subject: str, extra: dict[str, Any] | None = None
) -> tuple[str, int]:
    """Return (token, expires_in_seconds). Short-lived (default 15 min)."""
    settings = get_settings()
    minutes = settings.jwt_access_token_expires_minutes
    exp = datetime.now(UTC) + timedelta(minutes=minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": exp,
        "iat": datetime.now(UTC),
        "typ": "access",
        # Per-token jti for revocation list. Older access tokens (issued
        # before v0.8.0 deploy) lack jti; the verification path treats
        # missing jti as "skip revocation check" so they keep working
        # naturally for up to 15 min after deploy.
        "jti": secrets.token_urlsafe(16),
    }
    if extra:
        payload.update(extra)
    return _encode(payload), minutes * 60


def create_refresh_token(subject: str) -> tuple[str, int]:
    """Return (token, expires_in_seconds). Long-lived (default 7 days).

    Carries `typ=refresh` so endpoints can distinguish from access tokens
    and reject the wrong type. The session cookie carries access; the
    refresh cookie carries this one and is only sent to /auth/refresh.
    """
    settings = get_settings()
    days = settings.jwt_refresh_token_expires_days
    exp = datetime.now(UTC) + timedelta(days=days)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": exp,
        "iat": datetime.now(UTC),
        "typ": "refresh",
        # Per-token jti for future revocation list (not yet implemented).
        "jti": secrets.token_urlsafe(16),
    }
    return _encode(payload), days * 24 * 3600


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any] | None:
    """Decode and verify token type. Returns None on any verification failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        return None
    if payload.get("typ") != expected_type:
        return None
    return payload


def decode_access_token(token: str) -> dict[str, Any] | None:
    return decode_token(token, "access")


def decode_refresh_token(token: str) -> dict[str, Any] | None:
    return decode_token(token, "refresh")


def generate_csrf_token() -> str:
    """Cryptographically secure random CSRF token (~256 bits).

    Stored in a NON-httpOnly cookie so the SPA can read it and echo back
    in `X-CSRF-Token` header on mutating requests. Server validates the
    header matches the cookie (double-submit pattern). XSS that can read
    the CSRF cookie would also have full DOM access — but our session
    cookie is httpOnly, so XSS still can't read the auth credential.
    Combined with SameSite=Strict on the session cookie, this provides
    layered CSRF defense.
    """
    return secrets.token_urlsafe(32)


def constant_time_compare(a: str, b: str) -> bool:
    """Timing-attack-resistant string comparison."""
    return secrets.compare_digest(a, b)
