"""Bot defense policy snapshot."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BotDefensePolicy(Base):
    __tablename__ = "bot_defense_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "namespace", "name", name="uq_botpol_tenant_ns_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_shared: Mapped[bool] = mapped_column(nullable=False, default=False)

    protected_endpoint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    protected_paths: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    # Mitigation actions enabled
    has_javascript_challenge: Mapped[bool] = mapped_column(nullable=False, default=False)
    has_captcha_challenge: Mapped[bool] = mapped_column(nullable=False, default=False)
    has_redirect: Mapped[bool] = mapped_column(nullable=False, default=False)
    has_block: Mapped[bool] = mapped_column(nullable=False, default=False)

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
