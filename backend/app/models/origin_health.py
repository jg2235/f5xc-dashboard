"""Origin health snapshot — per (pool, origin, site) current state.

History deferred to a future slice (would be a partitioned events table).
This table holds CURRENT state only; updated by sync_healthchecks every
POLL_HEALTHCHECK_INTERVAL seconds.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OriginHealth(Base):
    __tablename__ = "origin_health"
    __table_args__ = (
        UniqueConstraint(
            "pool_id", "origin_address", "origin_port", "site_name",
            name="uq_origin_health_pool_origin_site",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("origin_pools.id", ondelete="CASCADE"), nullable=False, index=True
    )

    origin_address: Mapped[str] = mapped_column(String(255), nullable=False)
    origin_port: Mapped[int | None] = mapped_column(Integer, nullable=True)

    site_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    site_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # re | ce | virtual

    # Raw F5 XC status string (HEALTHY | UNHEALTHY | UNKNOWN | STARTING | DRAINING | ...)
    raw_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    # Operational classification: healthy | unhealthy | warning | info | unknown
    classified_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")

    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_status_change: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_probe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
