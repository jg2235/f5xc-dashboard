"""WAF / app_firewall policy snapshot."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AppFirewall(Base):
    """F5 XC `app_firewall` (WAF policy) snapshot.

    Lives in a namespace. Slice 3 indexes both the user's namespace and
    `shared` (where tenant-wide WAFs are typically defined).
    """
    __tablename__ = "app_firewalls"
    __table_args__ = (
        UniqueConstraint("tenant_id", "namespace", "name", name="uq_appfw_tenant_ns_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_shared: Mapped[bool] = mapped_column(nullable=False, default=False)

    # Top-level config (extracted by transformer)
    enforcement_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)  # blocking | monitoring
    default_anonymization: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_bot_setting: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detection_settings: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Signature categories: "owasp_top10" | "credit_card" | "ssn" | etc.
    enabled_signature_categories: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    blocked_attack_types: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    custom_rule_count: Mapped[int] = mapped_column(nullable=False, default=0)
    exclusion_rule_count: Mapped[int] = mapped_column(nullable=False, default=0)
    allowed_response_codes: Mapped[list[int]] = mapped_column(JSONB, nullable=True)

    raw_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
