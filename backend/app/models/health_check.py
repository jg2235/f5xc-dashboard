"""Health check config object snapshot.

F5 XC health checks are standalone objects referenced by origin pools
(spec.healthcheck[] → {name, namespace}). This table stores their parsed
configuration so the dashboard can show *how* a pool's health check is
configured, not just its name.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class HealthCheck(Base):
    __tablename__ = "health_checks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "namespace", "name", name="uq_healthcheck_tenant_ns_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # http | https | tcp | unknown
    protocol: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")

    # Common timing/threshold settings
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    healthy_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unhealthy_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    jitter_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # HTTP/HTTPS-specific
    http_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    http_host_header: Mapped[str | None] = mapped_column(String(255), nullable=True)
    http_use_http2: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    expected_status_codes: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    raw_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
