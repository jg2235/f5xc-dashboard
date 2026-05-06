"""Origin pool snapshot + healthcheck summary."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OriginPool(Base):
    __tablename__ = "origin_pools"
    __table_args__ = (
        UniqueConstraint("tenant_id", "namespace", "name", name="uq_pool_tenant_ns_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lb_algorithm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    origin_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Slice 2: pre-extracted origin string addresses (e.g., "203.0.113.10",
    # "k8s://my-svc"). Saves the healthcheck task from re-parsing raw_spec.
    origin_addresses: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    healthcheck_refs: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    # Rolled-up health (worst-case across all (origin, site) pairs for this pool)
    healthy_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unhealthy_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_healthcheck_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
