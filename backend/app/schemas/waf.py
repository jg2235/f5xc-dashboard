"""WAF analytics schemas (slice 4)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WafSparklinePoint(BaseModel):
    bucket_time: datetime
    request_count: int
    blocked_count: int
    monitored_count: int
    error_count: int


class WafSparkline(BaseModel):
    """24h @ 5-min sparkline for one LB (or aggregated tenant-wide if lb_name is None)."""
    lb_namespace: str | None = None
    lb_name: str | None = None
    points: list[WafSparklinePoint]
    total_requests: int
    total_blocked: int
    total_monitored: int
    total_errors: int


class TopKEntry(BaseModel):
    key: str
    count: int


class WafTopK(BaseModel):
    """Top-K for one dimension (source_ip, country, signature, url)."""
    dimension: str
    entries: list[TopKEntry]


class WafEventSummary(BaseModel):
    """Compact event row for the events drill-down table."""
    event_time: datetime
    lb_namespace: str
    lb_name: str
    action: str
    source_ip: str | None
    source_country: str | None
    method: str | None
    url: str | None
    response_code: int | None
    primary_signature: str | None
    severity: str | None


class WafOverviewStats(BaseModel):
    """Lightweight tenant-wide rollup for the dashboard hero cards."""
    window_minutes: int
    total_requests: int
    total_blocked: int
    total_monitored: int
    total_errors: int
    block_rate_pct: float
