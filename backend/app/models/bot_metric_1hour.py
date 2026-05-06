"""1-hour bot metric rollups.

Maintained by a TimescaleDB continuous aggregate from bot_metrics_1min.
NOT directly written to by the application — Alembic creates the
materialized view that maintains it on a 10-min refresh cycle.

Retention: 90 days.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BotMetric1Hour(Base):
    __tablename__ = "bot_metrics_1hour"

    bucket_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    lb_namespace: Mapped[str] = mapped_column(String(120), primary_key=True, nullable=False)
    lb_name: Mapped[str] = mapped_column(String(120), primary_key=True, nullable=False)

    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    challenge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    block_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allow_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
