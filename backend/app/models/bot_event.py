"""Raw bot events.

Becomes a TimescaleDB hypertable in slice 5 migration. Holds events from
two distinct sources merged into one shape:

  - source="standard"     → BD Standard via security_events (action+bot_defense fields)
  - source="bd_advanced"  → BD-A via /api/data/.../bot_traffic

Retention: 7 days, partitioned on event_time.

Per slice 5 decision (full taxonomy / option C), we capture:
  - action: ALLOW | CHALLENGE | BLOCK | MONITOR
  - bot_category: good_bot | bad_bot | automation | scraper |
                  data_center | search_engine | suspicious | human | unknown
  - confidence_bucket: low | medium | high  (only meaningful for BD-A)
  - challenge_result: passed | failed | abandoned | not_issued
  - device_anomalies: list of fingerprint anomaly tags

The discriminator + per-source nullable columns let one schema cover both
ingestion paths cleanly.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BotEvent(Base):
    __tablename__ = "bot_events"

    # Composite PK (event_time, id). event_time is the hypertable partition column.
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Soft FK by name+namespace (matches WAF event pattern)
    lb_namespace: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    lb_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    # standard | bd_advanced
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="standard", index=True)

    # Action — ALLOW | CHALLENGE | BLOCK | MONITOR
    action: Mapped[str] = mapped_column(String(16), nullable=False, default="ALLOW", index=True)

    # Full taxonomy
    # good_bot|bad_bot|automation|scraper|data_center|search_engine|suspicious|human|unknown
    bot_category: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown", index=True)
    # low | medium | high (BD-A only; "unknown" for Standard)
    confidence_bucket: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    confidence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0–100

    # Challenge metadata (BD-A primarily, but Standard also issues challenges)
    # passed | failed | abandoned | not_issued
    challenge_result: Mapped[str] = mapped_column(String(16), nullable=False, default="not_issued")
    challenge_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # js | captcha | redirect

    # Device telemetry (BD-A)
    device_anomalies: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # Source / network detail (mirrors WAF events)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_country: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    source_asn: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Endpoint targeting — slice 5 needs per-endpoint dashboards
    method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    endpoint_path: Mapped[str | None] = mapped_column(String(2048), nullable=True, index=True)

    # User agent — full string + extracted family (Chrome / curl / Go-http-client / etc.)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ua_family: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Optional reference back to the bot_defense_policy that decided
    bot_policy_namespace: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bot_policy_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    raw_event: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
