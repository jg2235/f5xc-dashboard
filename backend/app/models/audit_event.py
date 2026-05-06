"""Audit log.

Records security-relevant actions: login attempts (success+failure), logout,
sync triggers, alert state changes. Standard table, retention configurable
via AUDIT_RETENTION_DAYS (default 180).

The schema is intentionally generic so it can absorb new event types without
a migration: `event_type` is an enum-like string and `details` is JSONB.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Event types (free-form string, not an enum, so we don't need a migration
    # every time we add a new tracked action):
    #   auth.login.success / auth.login.failure / auth.logout / auth.refresh
    #   sync.trigger.<task>
    #   alert.acknowledge / alert.resolve / alert.reopen
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # The thing acted upon — e.g., username for login attempts, sync task name,
    # alert id. Free-form.
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False)  # success | failure | denied
    request_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
