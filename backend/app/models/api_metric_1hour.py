"""1-hour API endpoint metric rollups.

Maintained by a TimescaleDB continuous aggregate from api_metrics_1min.
NOT directly written by the app. Created in slice 6 Alembic migration.

Latency percentiles cannot be averaged across buckets without losing
accuracy — for the 1-hour rollup we use the MAX of the 1-min p99 (gives
worst-case in the hour) and AVG of the 1-min p50 (gives a soft typical).
This is documented intent, not bug.

Retention: 90 days.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ApiMetric1Hour(Base):
    __tablename__ = "api_metrics_1hour"

    bucket_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    lb_namespace: Mapped[str] = mapped_column(String(120), primary_key=True, nullable=False)
    lb_name: Mapped[str] = mapped_column(String(120), primary_key=True, nullable=False)
    method: Mapped[str] = mapped_column(String(16), primary_key=True, nullable=False)
    endpoint_path: Mapped[str] = mapped_column(String(2048), primary_key=True, nullable=False)

    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_4xx_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_5xx_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Aggregated latency — see module docstring for semantics
    latency_p50_avg_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_p95_max_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_p99_max_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
