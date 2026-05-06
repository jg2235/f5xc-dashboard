"""User CRUD service — CLI-only in v0.9.0 (no admin REST API).

Design rationale: dashboard admins should NOT create users via a web UI.
User provisioning is an ops concern handled via `make user-add` and friends.
The dashboard authenticates against this table but doesn't expose write
operations through HTTP.

Mirrors app.services.tenants in shape: pure logic, custom exceptions,
caller commits. CLI in backend/scripts/user_cli.py imports from here.

Public surface:
    list_users(db, *, tenant_id=None) -> list[User]
    get_user(db, user_id_or_username) -> User
    create_user(db, *, username, email, password, tenant_id, role) -> User
    set_password(db, user_id, *, new_password) -> User
    set_role(db, user_id, *, role) -> User
    set_active(db, user_id, *, is_active) -> User

Last-active-admin protection: set_active(is_active=False) and any
deactivation path refuses to flip the only remaining active admin off.
This prevents the system from being locked into a zero-admin state.
"""
from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.logging_config import get_logger
from app.models import Tenant, User

log = get_logger(__name__)

ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
VALID_ROLES = frozenset({ROLE_ADMIN, ROLE_VIEWER})


class UserServiceError(Exception):
    pass


class UserNotFound(UserServiceError):
    pass


class DuplicateUsername(UserServiceError):
    pass


class TenantNotFoundForAssignment(UserServiceError):
    pass


class LastActiveAdminError(UserServiceError):
    """Refuse to deactivate or change role of the last active admin."""


def _resolve_user(db: Session, id_or_username: str | uuid.UUID) -> User:
    """Resolve User by UUID or username. Raises UserNotFound."""
    if isinstance(id_or_username, uuid.UUID):
        user = db.get(User, id_or_username)
        if user is None:
            raise UserNotFound(f"no user with id {id_or_username}")
        return user
    # Try UUID parse
    try:
        u = uuid.UUID(str(id_or_username))
        user = db.get(User, u)
        if user is not None:
            return user
    except ValueError:
        pass
    # Username fallback
    user = db.execute(
        select(User).where(User.username == str(id_or_username))
    ).scalar_one_or_none()
    if user is None:
        raise UserNotFound(f"no user matching {id_or_username!r} (by id or username)")
    return user


def _count_active_admins(db: Session, exclude_user_id: uuid.UUID | None = None) -> int:
    """How many active admins exist? Excludes the candidate user being modified."""
    stmt = select(func.count()).select_from(User).where(
        User.role == ROLE_ADMIN,
        User.is_active == True,  # noqa: E712 — SQL boolean
    )
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return db.execute(stmt).scalar_one()


def list_users(db: Session, *, tenant_id: uuid.UUID | None = None) -> list[User]:
    """List users. Optionally filter by tenant_id."""
    stmt = select(User).order_by(User.username)
    if tenant_id is not None:
        stmt = stmt.where(User.tenant_id == tenant_id)
    return list(db.execute(stmt).scalars().all())


def get_user(db: Session, id_or_username: str | uuid.UUID) -> User:
    """Resolve by id OR username. Raises UserNotFound."""
    return _resolve_user(db, id_or_username)


def create_user(
    db: Session,
    *,
    username: str,
    email: str | None,
    password: str,
    tenant_id: uuid.UUID,
    role: Literal["admin", "viewer"] = ROLE_VIEWER,
) -> User:
    """Create a user assigned to a tenant. Caller commits."""
    if role not in VALID_ROLES:
        raise UserServiceError(f"invalid role {role!r} (must be: {sorted(VALID_ROLES)})")
    if len(password) < 8:
        raise UserServiceError("password must be at least 8 characters")

    # Tenant must exist
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise TenantNotFoundForAssignment(f"no tenant with id {tenant_id}")

    # Username uniqueness (DB constraint as final guard, but pre-flight is friendlier)
    existing = db.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateUsername(f"username {username!r} already in use")

    user = User(
        tenant_id=tenant_id,
        username=username,
        email=email,
        hashed_password=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    log.info(
        "user_created",
        user_id=str(user.id),
        username=username,
        tenant_id=str(tenant_id),
        role=role,
    )
    return user


def set_password(
    db: Session, id_or_username: str | uuid.UUID, *, new_password: str
) -> User:
    """Re-hash + persist a new password."""
    if len(new_password) < 8:
        raise UserServiceError("password must be at least 8 characters")
    user = _resolve_user(db, id_or_username)
    user.hashed_password = hash_password(new_password)
    db.flush()
    log.info("user_password_rotated", user_id=str(user.id), username=user.username)
    return user


def set_role(
    db: Session, id_or_username: str | uuid.UUID, *, role: str
) -> User:
    """Change role. Refuses to demote the last active admin."""
    if role not in VALID_ROLES:
        raise UserServiceError(f"invalid role {role!r} (must be: {sorted(VALID_ROLES)})")
    user = _resolve_user(db, id_or_username)

    # If demoting an active admin, ensure another active admin remains
    if user.role == ROLE_ADMIN and role != ROLE_ADMIN and user.is_active:
        remaining = _count_active_admins(db, exclude_user_id=user.id)
        if remaining == 0:
            raise LastActiveAdminError(
                f"refusing to demote {user.username!r}: last active admin"
            )

    user.role = role
    db.flush()
    log.info("user_role_changed", user_id=str(user.id), username=user.username, new_role=role)
    return user


def set_active(
    db: Session, id_or_username: str | uuid.UUID, *, is_active: bool
) -> User:
    """Activate or deactivate. Refuses to deactivate the last active admin."""
    user = _resolve_user(db, id_or_username)

    if user.is_active and not is_active and user.role == ROLE_ADMIN:
        remaining = _count_active_admins(db, exclude_user_id=user.id)
        if remaining == 0:
            raise LastActiveAdminError(
                f"refusing to deactivate {user.username!r}: last active admin"
            )

    user.is_active = is_active
    db.flush()
    log.info(
        "user_active_changed",
        user_id=str(user.id),
        username=user.username,
        is_active=is_active,
    )
    return user


__all__ = [
    "UserServiceError",
    "UserNotFound",
    "DuplicateUsername",
    "TenantNotFoundForAssignment",
    "LastActiveAdminError",
    "ROLE_ADMIN",
    "ROLE_VIEWER",
    "VALID_ROLES",
    "list_users",
    "get_user",
    "create_user",
    "set_password",
    "set_role",
    "set_active",
]
