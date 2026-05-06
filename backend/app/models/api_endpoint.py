"""Discovered API endpoints.

Slice 6 inventory model. F5 XC's ML discovery surface produces a list of
endpoints per HTTP LB (regardless of whether you've declared them in an
api_definition). We track each unique (lb, method, path) tuple along with
discovery metadata.

This is NOT a hypertable — the endpoint count is bounded (typical: 50-500
per LB, ceiling somewhere around 5k for very large APIs). Standard table.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ApiEndpoint(Base):
    __tablename__ = "api_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # LB ownership — soft FK by name+namespace, mirrors slice 4/5 pattern
    lb_namespace: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    lb_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    # Endpoint identity
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    endpoint_path: Mapped[str] = mapped_column(String(2048), nullable=False)

    # Discovery linkage — was this declared in an api_definition or only ML-found?
    # is_shadow=True means F5 XC discovered it but no api_definition references it.
    # Operators care about this — it's the "what API surface exists that we
    # didn't know about?" signal.
    is_shadow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    api_definition_namespace: Mapped[str | None] = mapped_column(String(120), nullable=True)
    api_definition_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # F5 XC ML metadata
    # 0–100. How confident is the discovery model in the inferred shape.
    discovery_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Aggregate traffic counts (refreshed each sync)
    total_request_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Inferred shape (slice 6 option B for question 3)
    # response_codes: list of integers seen ([200, 201, 400, 404])
    response_codes: Mapped[list[int] | None] = mapped_column(
        ARRAY(Integer), nullable=True
    )
    # query_params: list of {name, type, required} dicts
    query_params: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    # body_params: list of {name, type, required} dicts (for POST/PUT/PATCH)
    body_params: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    # Authentication type observed: none | basic | bearer | oauth | apikey | unknown
    auth_type: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)

    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "lb_namespace", "lb_name", "method", "endpoint_path",
            name="uq_api_endpoint_identity",
        ),
    )
