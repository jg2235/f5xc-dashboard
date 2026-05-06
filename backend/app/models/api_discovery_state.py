"""Per-LB API discovery ML state.

F5 XC's ML model has a lifecycle:
  - learning   — collecting traffic, not yet stable
  - mature     — learned baseline, ready to enforce
  - enforcing  — schema validation active
  - disabled   — discovery turned off
  - unknown    — no signal

We surface this per HTTP LB (the ML model is per-LB, not per-api_definition).
This is a small slowly-changing table — one row per LB.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ApiDiscoveryState(Base):
    __tablename__ = "api_discovery_states"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lb_namespace: Mapped[str] = mapped_column(String(120), nullable=False)
    lb_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    # learning | mature | enforcing | disabled | unknown
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown", index=True)
    # 0–100 — how confident is the ML model in the current state classification
    confidence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    total_endpoints_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_traffic_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_learning_update: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    state_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "lb_namespace", "lb_name",
            name="uq_api_discovery_state_lb",
        ),
    )
