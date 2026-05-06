"""Policy ↔ LB attachment table.

Maps `(policy_type, policy_namespace, policy_name) → load_balancer_id`. Populated
by `sync_loadbalancers` whenever it inspects the LB raw_spec — gives O(1)
reverse lookup for "which LBs are using this policy" without scanning JSONB.

Slice 3 builds this from the same data we already extract for
`has_waf` / `has_service_policy` / `has_bot_defense` / `has_api_protection`,
so there's no extra F5 XC API call cost.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PolicyAttachment(Base):
    __tablename__ = "policy_attachments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "policy_type", "policy_namespace", "policy_name", "lb_id",
            name="uq_polatt_full",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # One of: app_firewall | service_policy | bot_defense_policy | api_definition
    policy_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    policy_namespace: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    policy_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    lb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("load_balancers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
