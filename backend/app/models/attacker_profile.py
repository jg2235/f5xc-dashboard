"""Cross-signal attacker profile.

Slice 7 correlator output. Each row groups events from waf_events,
bot_events, and api_metrics_1min by (source_ip, source_asn, source_country)
within a recent window, producing the operator's threat-actor view.

NOT a hypertable — bounded cardinality (one row per attacker grouping).
Refreshed on each cycle — last_window_minutes determines what's "recent."

Identity is (tenant_id, source_ip, source_asn, source_country). ASN may
be NULL (lookup failures). Country may be NULL (private/internal IPs).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AttackerProfile(Base):
    __tablename__ = "attacker_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_asn: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_country: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)

    # Cross-signal counts (within profile window)
    waf_block_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    waf_monitor_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bot_block_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bot_challenge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_4xx_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Total event count for sorting (sum of all signals above)
    total_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)

    # Top targeted endpoint (most-hit URL/path across signals)
    top_endpoint: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Top WAF signature, if any
    top_signature: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Distinct LBs touched
    distinct_lbs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_ip", "source_asn", "source_country",
            name="uq_attacker_profile_identity",
        ),
    )
