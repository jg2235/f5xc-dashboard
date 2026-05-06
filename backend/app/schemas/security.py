"""Security analytics + alert schemas (slice 7)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SecurityOverviewStats(BaseModel):
    """Tenant-wide cross-signal threat summary."""
    window_minutes: int
    total_attackers: int
    countries_seen: int
    top_country: str | None
    top_country_count: int
    total_waf_blocks: int
    total_bot_interventions: int   # bot block + challenge
    total_api_4xx: int
    open_alerts: int
    critical_alerts: int


class GeoEntry(BaseModel):
    """Country-level event count for choropleth."""
    country: str
    count: int


class AttackerProfileSummary(BaseModel):
    id: str
    source_ip: str
    source_asn: int | None
    source_country: str | None
    waf_block_count: int
    waf_monitor_count: int
    bot_block_count: int
    bot_challenge_count: int
    api_4xx_count: int
    total_events: int
    top_endpoint: str | None
    top_signature: str | None
    distinct_lbs: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None


class AttackerTimelineEntry(BaseModel):
    event_time: datetime
    signal: str            # waf | bot
    action: str
    lb_name: str | None
    method: str | None
    endpoint: str | None
    classifier: str | None  # signature for WAF, bot_category for Bot
    rsp_code: int | None
    severity: str | None
    extra: dict[str, Any] | None


class AlertOut(BaseModel):
    id: str
    rule_id: str
    severity: str
    status: str
    dedupe_key: str
    title: str
    description: str
    context: dict[str, Any]
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class AlertActionResult(BaseModel):
    """Response for ack/resolve actions."""
    id: str
    status: str
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class AlertSummaryStats(BaseModel):
    open: int
    acknowledged: int
    resolved: int
    critical: int
    warning: int
    info: int
