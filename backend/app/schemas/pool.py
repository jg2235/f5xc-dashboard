"""Origin pool API schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

OriginStatus = Literal["healthy", "unhealthy", "warning", "info", "unknown"]


class OriginHealthCell(BaseModel):
    """One (origin, site) cell in the health matrix."""
    origin_address: str
    origin_port: int | None
    site_name: str
    site_type: str | None
    raw_status: str
    classified_status: OriginStatus
    consecutive_failures: int
    last_status_change: datetime | None
    last_probe_at: datetime | None


class OriginPoolSummary(BaseModel):
    id: uuid.UUID
    namespace: str
    name: str
    port: int | None
    lb_algorithm: str | None
    origin_count: int
    healthy_count: int
    unhealthy_count: int
    warning_count: int
    last_healthcheck_at: datetime | None
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class OriginPoolDetail(OriginPoolSummary):
    """Pool with full origin × site health matrix + raw spec."""
    origin_addresses: list[str]
    site_names: list[str]                   # union of all sites that have health rows
    healthcheck_refs: list[str] | None
    health_matrix: list[OriginHealthCell]
    raw_spec: dict[str, Any]


class PoolStats(BaseModel):
    total_pools: int
    pools_with_unhealthy: int
    pools_with_warnings: int
    total_origins: int
    unhealthy_cells: int                    # (origin, site) cells with unhealthy status
    warning_cells: int
