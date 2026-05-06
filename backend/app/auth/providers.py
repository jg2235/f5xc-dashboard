"""Pluggable auth providers.

Local: bcrypt password check against users table.
OIDC : stub that raises NotImplemented — wired into FastAPI but not active.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import verify_password
from app.config import Settings, get_settings
from app.logging_config import get_logger
from app.models import User

log = get_logger(__name__)


class AuthProvider(ABC):
    @abstractmethod
    def authenticate(self, db: Session, username: str, password: str) -> User | None: ...


class LocalAuthProvider(AuthProvider):
    def authenticate(self, db: Session, username: str, password: str) -> User | None:
        user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if user is None or not user.is_active or not user.hashed_password:
            return None
        if not verify_password(password, user.hashed_password):
            log.info("auth_failed", username=username, reason="bad_password")
            return None
        return user


class OIDCAuthProvider(AuthProvider):
    """Stub. Real implementation will exchange code→tokens→userinfo."""

    def authenticate(self, db: Session, username: str, password: str) -> User | None:  # noqa: ARG002
        raise NotImplementedError(
            "OIDC provider is a stub in v1. Set AUTH_PROVIDER=local. "
            "See docs/OIDC.md for the planned implementation."
        )


def get_auth_provider(settings: Settings | None = None) -> AuthProvider:
    s = settings or get_settings()
    if s.auth_provider == "oidc":
        return OIDCAuthProvider()
    return LocalAuthProvider()
