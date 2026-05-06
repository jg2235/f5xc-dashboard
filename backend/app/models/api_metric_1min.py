"""1-minute API endpoint metric rollups.

Slice 6 — per-endpoint time-series. Pulled from F5 XC's metrics_multi_v2
endpoint with API-specific metric names + per-endpoint dimension labels.

Hypertable partitioned on bucket_time, retention 30 days. The 1-hour
rollup (api_metrics_1hour) is maintained by a TimescaleDB continuous aggregate.

Per slice 6 question 4 default (option B): captures latency p50/p95/p99
because they come "for free" from F5 XC's metrics endpoint.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ApiMetric1Min(Base):
    __tablename__ = "api_metrics_1min"

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
    method: Mapped[str] = mapped_column(String(16), primary_key=True, nullable=False)
    endpoint_path: Mapped[str] = mapped_column(String(2048), primary_key=True, nullable=False)

    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_4xx_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_5xx_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Latency percentiles in milliseconds. Float because F5 XC returns sub-ms precision.
    latency_p50_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_p99_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
