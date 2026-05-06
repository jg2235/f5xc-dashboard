"""Service policy snapshot — F5 XC `service_policy` (note F5's plural is `service_policys`)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ServicePolicy(Base):
    __tablename__ = "service_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "namespace", "name", name="uq_svcpol_tenant_ns_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_shared: Mapped[bool] = mapped_column(nullable=False, default=False)

    # Default action for non-matching traffic
    # ALLOW | DENY | NEXT_POLICY
    default_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rule_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Counts of rule actions
    allow_rule_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deny_rule_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Surface notable rule attributes from sync transform
    has_geo_rules: Mapped[bool] = mapped_column(nullable=False, default=False)
    has_ip_rules: Mapped[bool] = mapped_column(nullable=False, default=False)
    has_path_rules: Mapped[bool] = mapped_column(nullable=False, default=False)

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
