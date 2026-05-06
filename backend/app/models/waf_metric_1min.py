"""1-minute WAF metric rollups.

Populated by sync_waf_metrics task pulling from F5 XC's metrics API.
Stored separately from WafEvent because:
  - Metrics API gives pre-aggregated counters cheaply (no per-event scan)
  - Different retention (30d vs 7d for raw events)
  - Used directly for sparkline rendering — no scan of raw events needed

Hypertable partitioned on bucket_time. Retention: 30 days.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WafMetric1Min(Base):
    __tablename__ = "waf_metrics_1min"

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
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monitored_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 5xx response

    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
