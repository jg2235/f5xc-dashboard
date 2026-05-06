"""1-minute bot metric rollups.

Pulled from F5 XC's metrics_multi_v2 endpoint with bot-specific metric names:
  - loadbalancer.bot_request_count    (total requests evaluated by bot defense)
  - loadbalancer.bot_challenge_count  (challenges issued)
  - loadbalancer.bot_block_count      (outright blocks)
  - loadbalancer.bot_allow_count      (passed challenges + good_bot allows)

Stored separately from BotEvent because:
  - cheap polling, used directly for sparklines
  - different retention (30d vs 7d)
  - aggregates avoid scanning raw event hypertable for the common "show me a chart" query

Hypertable partitioned on bucket_time. Retention: 30 days.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BotMetric1Min(Base):
    __tablename__ = "bot_metrics_1min"

    bucket_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        index=True,
    )
    lb_namespace: Mapped[str] = mapped_column(String(120), primary_key=True, nullable=False)
    lb_name: Mapped[str] = mapped_column(String(120), primary_key=True, nullable=False)

    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    challenge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    block_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allow_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
