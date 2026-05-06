"""Alert log.

Slice 7 alerting (in-dashboard only — option A). Standard table, retention
90 days enforced via cleanup task (no hypertable since cardinality is low —
expect tens to hundreds of alerts per day on a busy tenant).

Status flow:
  open → acknowledged → resolved
  open → resolved (skip ack)

Alerts are deduplicated by (tenant_id, rule_id, dedupe_key). Re-firing the
same rule for the same dedupe target updates last_seen_at and bumps
occurrence_count rather than creating a new row.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Rule identity — string id like "waf.block_burst", "bot.cred_stuffing", etc.
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # critical | warning | info
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info", index=True)
    # open | acknowledged | resolved
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)

    # Dedup key — within a rule, same key = same logical alert. Examples:
    #   waf.block_burst dedupe_key = "lb:www-prod-lb"
    #   bot.cred_stuffing dedupe_key = "ip:198.51.100.99"
    #   api.shadow_emergence dedupe_key = "ep:api-prod-lb:GET:/api/v2/admin"
    dedupe_key: Mapped[str] = mapped_column(String(256), nullable=False)

    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(String(2048), nullable=False, default="")

    # Structured context — populated by the rule (counts, IPs, endpoint, etc.)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "rule_id", "dedupe_key",
            name="uq_alert_dedup_identity",
        ),
    )
