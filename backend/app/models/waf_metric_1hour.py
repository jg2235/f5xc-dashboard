"""1-hour WAF metric rollups.

Populated automatically by a TimescaleDB continuous aggregate from
waf_metrics_1min. NOT directly written to by the application — Alembic
creates the materialized view that maintains it.

Retention: 90 days.

This model exists only so SQLAlchemy can read from the view. It's marked
with __mapper_args__["primary_key"] explicitly because views don't have
a real PK at the DB level.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WafMetric1Hour(Base):
    __tablename__ = "waf_metrics_1hour"

    bucket_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    lb_namespace: Mapped[str] = mapped_column(String(120), primary_key=True, nullable=False)
    lb_name: Mapped[str] = mapped_column(String(120), primary_key=True, nullable=False)

    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monitored_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
