"""API analytics schemas (slice 6)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ApiDiscoveryStateOut(BaseModel):
    lb_namespace: str
    lb_name: str
    state: str  # learning | mature | enforcing | disabled | unknown
    confidence_score: int | None
    total_endpoints_discovered: int
    total_traffic_samples: int
    last_learning_update: datetime | None
    state_changed_at: datetime | None


class ApiOverviewStats(BaseModel):
    """Tenant-wide API discovery + traffic rollup."""
    total_endpoints: int
    shadow_endpoints: int
    declared_endpoints: int
    state_counts: dict[str, int]   # {"learning": 1, "mature": 2, "enforcing": 1, ...}
    avg_p99_latency_ms: float | None
    error_rate_pct: float          # 4xx + 5xx / total in window
    window_minutes: int


class ApiEndpointSummary(BaseModel):
    """Compact endpoint row for inventory tables."""
    id: str
    lb_namespace: str
    lb_name: str
    method: str
    endpoint_path: str
    is_shadow: bool
    api_definition_namespace: str | None
    api_definition_name: str | None
    discovery_confidence: int | None
    total_request_samples: int
    last_seen_at: datetime | None
    auth_type: str | None
    response_codes: list[int] | None


class ApiEndpointDetail(ApiEndpointSummary):
    """Full endpoint detail including inferred shape."""
    first_seen_at: datetime | None
    query_params: list[dict[str, Any]] | None
    body_params: list[dict[str, Any]] | None


class ApiSparklinePoint(BaseModel):
    bucket_time: datetime
    request_count: int
    error_4xx_count: int
    error_5xx_count: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    latency_p99_ms: float | None


class ApiEndpointSparkline(BaseModel):
    """Time-series for a single endpoint or aggregate."""
    method: str | None
    endpoint_path: str | None
    points: list[ApiSparklinePoint]
    total_requests: int
    total_4xx: int
    total_5xx: int
    max_p99_ms: float | None


class ApiTopKEntry(BaseModel):
    key: str
    count: int  # used for both volume and 1000*latency representations


class ApiTopK(BaseModel):
    dimension: str
    entries: list[ApiTopKEntry]
