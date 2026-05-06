"""Helpers for writing audit events.

Use `record_audit()` from request handlers to log security-relevant actions.
The function is intentionally tolerant — never raises on insert failure (we
don't want audit-log issues to break user-facing operations). On failure it
logs to the structured logger and continues.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import Request
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import AuditEvent

log = get_logger(__name__)

Result = Literal["success", "failure", "denied"]


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    # Caddy sets X-Forwarded-For. Trust only the leftmost entry.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or None
    if request.client:
        return request.client.host
    return None


def _user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.headers.get("user-agent", "")[:500] or None


def record_audit(
    db: Session,
    *,
    event_type: str,
    result: Result,
    request: Request | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_username: str | None = None,
    tenant_id: uuid.UUID | None = None,
    target: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    try:
        event = AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_username=actor_username[:120] if actor_username else None,
            event_type=event_type[:80],
            target=target[:255] if target else None,
            result=result,
            request_ip=_client_ip(request),
            user_agent=_user_agent(request),
            details=details,
        )
        db.add(event)
        db.commit()
    except Exception as e:  # noqa: BLE001
        # Audit logging must not break the user-facing flow.
        log.warning("audit_event_write_failed", event_type=event_type, error=str(e))
