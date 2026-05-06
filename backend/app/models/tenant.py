"""Tenant model — one row per F5 XC tenant/namespace pair served by the dashboard."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    f5xc_tenant: Mapped[str] = mapped_column(String(120), nullable=False)
    f5xc_namespace: Mapped[str] = mapped_column(String(120), nullable=False)
    # v0.9.0 — multi-namespace list. The dashboard auths against ONE F5 XC
    # tenant + ONE token, but watches MULTIPLE namespaces within it.
    # Read via `effective_namespaces` property which falls back to
    # [f5xc_namespace] if this is NULL (backward compat for unmigrated rows).
    namespaces: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(length=120)), nullable=True, default=None
    )
    # Token stored plaintext in v1 (single-tenant); v2 will move to KMS-wrapped or secret backend.
    # Per-tenant token override. NULL = use env (settings.f5xc_api_token).
    # See sync tasks: settings.f5xc_api_token wins; tenant.f5xc_api_token is fallback.
    f5xc_api_token: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def effective_namespaces(self) -> list[str]:
        """Return the namespaces this tenant watches.

        Read precedence:
          1. `namespaces` array column (post-v0.9.0)
          2. `[f5xc_namespace]` (legacy fallback for rows not yet migrated)

        Always returns a non-empty list. Sync tasks iterate this directly.
        """
        if self.namespaces:
            return list(self.namespaces)
        return [self.f5xc_namespace]

    def __repr__(self) -> str:
        return f"<Tenant {self.name} ({self.f5xc_tenant}/{self.f5xc_namespace})>"
