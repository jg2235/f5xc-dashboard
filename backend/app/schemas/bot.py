"""Bot analytics schemas (slice 5)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BotSparklinePoint(BaseModel):
    bucket_time: datetime
    request_count: int
    challenge_count: int
    block_count: int
    allow_count: int


class BotSparkline(BaseModel):
    """24h @ 5-min sparkline. Tenant-wide if lb_name is None."""
    lb_namespace: str | None = None
    lb_name: str | None = None
    points: list[BotSparklinePoint]
    total_requests: int
    total_challenges: int
    total_blocks: int
    total_allows: int


class BotTopKEntry(BaseModel):
    key: str
    count: int


class BotTopK(BaseModel):
    dimension: str
    entries: list[BotTopKEntry]


class BotEventSummary(BaseModel):
    """Compact event row for the events drill-down table."""
    event_time: datetime
    lb_namespace: str
    lb_name: str
    source: str  # standard | bd_advanced
    action: str
    bot_category: str
    confidence_bucket: str
    confidence_score: int | None
    challenge_result: str
    challenge_type: str | None
    source_ip: str | None
    source_country: str | None
    source_asn: int | None
    method: str | None
    endpoint_path: str | None
    ua_family: str | None
    user_agent: str | None
    device_anomalies: list[str] | None


class BotOverviewStats(BaseModel):
    """Lightweight tenant-wide rollup for the dashboard hero cards."""
    window_minutes: int
    total_requests: int
    total_challenges: int
    total_blocks: int
    total_allows: int
    challenge_rate_pct: float
    block_rate_pct: float


class BotEndpointStats(BaseModel):
    """Per-endpoint aggregate. Powers the endpoints breakdown page."""
    endpoint_path: str
    method: str | None
    total_events: int
    challenge_count: int
    block_count: int
    allow_count: int
    monitor_count: int
    distinct_source_ips: int
    top_bot_category: str | None
    last_seen_at: datetime
