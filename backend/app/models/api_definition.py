"""API definition / spec snapshot."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ApiDefinition(Base):
    __tablename__ = "api_definitions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "namespace", "name", name="uq_apidef_tenant_ns_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_shared: Mapped[bool] = mapped_column(nullable=False, default=False)

    spec_format: Mapped[str | None] = mapped_column(String(32), nullable=True)  # openapi | swagger
    api_specs_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    endpoint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_validation_rules: Mapped[bool] = mapped_column(nullable=False, default=False)

    raw_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Slice 6 — list of {method, path, ...} dicts extracted from raw_spec.
    # Used for shadow-endpoint detection (declared vs ML-discovered).
    declared_endpoints: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    # Real F5 XC shape — object_store URL refs to the OpenAPI/swagger documents
    # (the console's "OpenAPI Specification Files" panel).
    swagger_spec_files: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Normalized api_groups: [{name, element_count, elements:[{methods, path_regex}]}].
    # Mirrors the console's "Api Groups" table + per-group operations drill-down.
    api_groups: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # Display label for the schema-update strategy, e.g. "Strict Schema Origin".
    schema_update_strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
