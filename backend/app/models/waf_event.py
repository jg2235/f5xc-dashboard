"""Raw WAF security events.

Becomes a TimescaleDB hypertable in slice 4 migration. The PK is composite
(event_time, id) because hypertable partitioning requires the partition
column to be in any unique constraint.

Retention: 7 days (drop_chunks policy applied via Alembic).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WafEvent(Base):
    __tablename__ = "waf_events"

    # Composite PK (event_time, id). event_time is the hypertable partition column.
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False, index=True
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # LB the event belongs to. Soft FK by name+namespace so deletions don't break partitioning.
    lb_namespace: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    lb_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    # Event details extracted from F5 XC security_events shape
    # ALLOW | BLOCK | MONITOR
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="ALLOW")
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_country: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    source_asn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Top violation/signature info
    primary_signature: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    signature_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    threat_categories: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # critical | high | medium | low | info
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Optional reference to which app_firewall policy made the decision
    waf_policy_namespace: Mapped[str | None] = mapped_column(String(120), nullable=True)
    waf_policy_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    raw_event: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
