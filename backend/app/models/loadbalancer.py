"""HTTP Load Balancer snapshot — latest config pulled from F5 XC."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class LoadBalancer(Base):
    __tablename__ = "load_balancers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "namespace", "name", name="uq_lb_tenant_ns_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # Extracted summary fields for fast dashboard queries
    domains: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    lb_type: Mapped[str] = mapped_column(String(32), nullable=False, default="http")  # http | https
    advertise_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Slice 2: explicit list of site names where the LB is advertised. For
    # advertise_on_public_default_vip we record the sentinel "__all_re__" and the
    # sync_healthchecks task expands it to every RE site it knows about.
    advertised_sites: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    has_waf: Mapped[bool] = mapped_column(nullable=False, default=False)
    has_service_policy: Mapped[bool] = mapped_column(nullable=False, default=False)
    has_bot_defense: Mapped[bool] = mapped_column(nullable=False, default=False)
    has_api_protection: Mapped[bool] = mapped_column(nullable=False, default=False)
    origin_pool_refs: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    cert_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

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
