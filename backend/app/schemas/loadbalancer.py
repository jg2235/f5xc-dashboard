"""LoadBalancer API schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.pool import OriginPoolSummary


class LoadBalancerSummary(BaseModel):
    """Compact row for dashboard table."""
    id: uuid.UUID
    namespace: str
    name: str
    domains: list[str]
    lb_type: str
    advertise_mode: str | None
    advertised_sites: list[str]
    has_waf: bool
    has_service_policy: bool
    has_bot_defense: bool
    has_api_protection: bool
    origin_pool_refs: list[str]
    cert_ref: str | None
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class LoadBalancerOut(LoadBalancerSummary):
    """Full LB record including raw spec."""
    raw_spec: dict[str, Any]


class LoadBalancerDetail(LoadBalancerSummary):
    """LB drill-down with linked pool health rolled up."""
    raw_spec: dict[str, Any]
    pools: list[OriginPoolSummary]


class LoadBalancerStats(BaseModel):
    total: int
    with_waf: int
    with_bot_defense: int
    with_api_protection: int
    with_service_policy: int
    https: int
    http_only: int
