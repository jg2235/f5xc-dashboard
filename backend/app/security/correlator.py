"""Attacker profile correlator (slice 7).

Reads from waf_events, bot_events, and api_metrics_1min within a window
and produces (source_ip, source_asn, source_country) groupings with
per-signal counts. Slice 7 decision option B for question 1: source IP +
ASN + country (not full fingerprint).

This module is the analytical core of slice 7. Sync task wraps it.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import AttackerProfile, BotEvent, WafEvent


@dataclass
class AttackerKey:
    source_ip: str
    source_asn: int | None
    source_country: str | None

    def as_tuple(self) -> tuple[str, int | None, str | None]:
        return (self.source_ip, self.source_asn, self.source_country)


@dataclass
class AttackerAggregates:
    waf_block: int = 0
    waf_monitor: int = 0
    bot_block: int = 0
    bot_challenge: int = 0
    api_4xx: int = 0
    endpoints: dict[str, int] = field(default_factory=dict)
    signatures: dict[str, int] = field(default_factory=dict)
    lbs: set[str] = field(default_factory=set)
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    def add_event_meta(
        self, *, lb_namespace: str, lb_name: str,
        endpoint: str | None, signature: str | None, event_time: datetime,
    ) -> None:
        if endpoint:
            self.endpoints[endpoint] = self.endpoints.get(endpoint, 0) + 1
        if signature:
            self.signatures[signature] = self.signatures.get(signature, 0) + 1
        self.lbs.add(f"{lb_namespace}/{lb_name}")
        if self.first_seen is None or event_time < self.first_seen:
            self.first_seen = event_time
        if self.last_seen is None or event_time > self.last_seen:
            self.last_seen = event_time

    @property
    def total(self) -> int:
        return (
            self.waf_block + self.waf_monitor
            + self.bot_block + self.bot_challenge
            + self.api_4xx
        )

    @property
    def top_endpoint(self) -> str | None:
        if not self.endpoints:
            return None
        return max(self.endpoints.items(), key=lambda kv: kv[1])[0]

    @property
    def top_signature(self) -> str | None:
        if not self.signatures:
            return None
        return max(self.signatures.items(), key=lambda kv: kv[1])[0]


def _key_from(ip: str | None, asn: int | None, country: str | None) -> AttackerKey | None:
    """Build attacker key. Returns None if source_ip is missing (unkeyed event)."""
    if not ip:
        return None
    return AttackerKey(source_ip=ip, source_asn=asn, source_country=country)


def correlate_attackers(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    window: timedelta,
    max_attackers: int = 2000,
) -> dict[tuple[str, int | None, str | None], AttackerAggregates]:
    """Build per-attacker cross-signal aggregates within the window.

    Returns a dict keyed by (source_ip, source_asn, source_country). Caller
    is responsible for upserting into attacker_profiles.

    Performance note: scans waf_events + bot_events for the window. Both
    are hypertables with chunk pruning, so a 24h window scans ~24 chunks
    on a 1-day chunk_time_interval. API 4xx counts come from api_metrics_1min
    (no source_ip dimension on metrics — we attribute API 4xx to attackers
    by joining with WAF events that hit the same endpoint, simplification).
    """
    end = datetime.now(UTC)
    start = end - window

    out: dict[tuple[str, int | None, str | None], AttackerAggregates] = {}

    # --- WAF events ---
    waf_rows: Iterable[Any] = db.execute(
        select(
            WafEvent.source_ip, WafEvent.source_asn, WafEvent.source_country,
            WafEvent.action, WafEvent.lb_namespace, WafEvent.lb_name,
            WafEvent.url, WafEvent.primary_signature, WafEvent.event_time,
        ).where(
            WafEvent.tenant_id == tenant_id,
            WafEvent.event_time >= start,
            WafEvent.event_time <= end,
            WafEvent.source_ip.is_not(None),
        )
    ).all()
    for r in waf_rows:
        key = _key_from(r.source_ip, r.source_asn, r.source_country)
        if key is None:
            continue
        agg = out.setdefault(key.as_tuple(), AttackerAggregates())
        if r.action == "BLOCK":
            agg.waf_block += 1
        elif r.action == "MONITOR":
            agg.waf_monitor += 1
        # ALLOW events don't make someone an attacker
        if r.action != "ALLOW":
            agg.add_event_meta(
                lb_namespace=r.lb_namespace, lb_name=r.lb_name,
                endpoint=r.url, signature=r.primary_signature,
                event_time=r.event_time,
            )

    # --- Bot events ---
    bot_rows = db.execute(
        select(
            BotEvent.source_ip, BotEvent.source_asn, BotEvent.source_country,
            BotEvent.action, BotEvent.lb_namespace, BotEvent.lb_name,
            BotEvent.endpoint_path, BotEvent.event_time,
        ).where(
            BotEvent.tenant_id == tenant_id,
            BotEvent.event_time >= start,
            BotEvent.event_time <= end,
            BotEvent.source_ip.is_not(None),
        )
    ).all()
    for r in bot_rows:
        key = _key_from(r.source_ip, r.source_asn, r.source_country)
        if key is None:
            continue
        agg = out.setdefault(key.as_tuple(), AttackerAggregates())
        if r.action == "BLOCK":
            agg.bot_block += 1
        elif r.action == "CHALLENGE":
            agg.bot_challenge += 1
        if r.action in ("BLOCK", "CHALLENGE", "MONITOR"):
            agg.add_event_meta(
                lb_namespace=r.lb_namespace, lb_name=r.lb_name,
                endpoint=r.endpoint_path, signature=None,
                event_time=r.event_time,
            )

    # --- API 4xx attribution ---
    # Limitation: api_metrics_1min has no source_ip dimension. We approximate
    # by counting WAF events with response_code 4xx as the attacker's API errors.
    # This is a documented simplification, captured in the slice 7 changelog.
    waf_4xx_rows = db.execute(
        select(
            WafEvent.source_ip, WafEvent.source_asn, WafEvent.source_country,
            func.count().label("c"),
        ).where(
            WafEvent.tenant_id == tenant_id,
            WafEvent.event_time >= start,
            WafEvent.event_time <= end,
            WafEvent.source_ip.is_not(None),
            WafEvent.response_code.between(400, 499),
        ).group_by(
            WafEvent.source_ip, WafEvent.source_asn, WafEvent.source_country,
        )
    ).all()
    for r in waf_4xx_rows:
        key = _key_from(r.source_ip, r.source_asn, r.source_country)
        if key is None:
            continue
        agg = out.setdefault(key.as_tuple(), AttackerAggregates())
        agg.api_4xx += int(r.c)

    # Truncate to max_attackers, keeping highest-volume
    if len(out) > max_attackers:
        ranked = sorted(out.items(), key=lambda kv: kv[1].total, reverse=True)[:max_attackers]
        out = dict(ranked)

    return out


def upsert_attacker_profiles(
    db: Session, *,
    tenant_id: uuid.UUID,
    aggregates: dict[tuple[str, int | None, str | None], AttackerAggregates],
) -> int:
    """Upsert correlator output into attacker_profiles. Returns row count.

    Identity is (tenant_id, source_ip, source_asn, source_country). We do
    NOT delete missing rows — operators may want to see "previously known"
    attackers fall out of the window. Cleanup happens via retention task.
    """
    n = 0
    for (ip, asn, country), agg in aggregates.items():
        stmt = insert(AttackerProfile).values(
            tenant_id=tenant_id,
            source_ip=ip,
            source_asn=asn,
            source_country=country,
            waf_block_count=agg.waf_block,
            waf_monitor_count=agg.waf_monitor,
            bot_block_count=agg.bot_block,
            bot_challenge_count=agg.bot_challenge,
            api_4xx_count=agg.api_4xx,
            total_events=agg.total,
            top_endpoint=agg.top_endpoint,
            top_signature=agg.top_signature,
            distinct_lbs=len(agg.lbs),
            first_seen_at=agg.first_seen,
            last_seen_at=agg.last_seen,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_attacker_profile_identity",
            set_={
                "waf_block_count": stmt.excluded.waf_block_count,
                "waf_monitor_count": stmt.excluded.waf_monitor_count,
                "bot_block_count": stmt.excluded.bot_block_count,
                "bot_challenge_count": stmt.excluded.bot_challenge_count,
                "api_4xx_count": stmt.excluded.api_4xx_count,
                "total_events": stmt.excluded.total_events,
                "top_endpoint": stmt.excluded.top_endpoint,
                "top_signature": stmt.excluded.top_signature,
                "distinct_lbs": stmt.excluded.distinct_lbs,
                "first_seen_at": func.least(
                    AttackerProfile.first_seen_at, stmt.excluded.first_seen_at,
                ),
                "last_seen_at": func.greatest(
                    AttackerProfile.last_seen_at, stmt.excluded.last_seen_at,
                ),
            },
        )
        db.execute(stmt)
        n += 1
    return n


def attacker_timeline(
    db: Session, *,
    tenant_id: uuid.UUID, source_ip: str,
    window: timedelta,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Per-attacker chronological event timeline for the drill-down page.

    Merges WAF and Bot events for the IP within the window. Sorted descending
    by event_time. Each entry has signal type, action, endpoint, signature/category.
    """
    end = datetime.now(UTC)
    start = end - window

    waf = db.execute(
        select(
            WafEvent.event_time, WafEvent.action, WafEvent.lb_name,
            WafEvent.url.label("endpoint"), WafEvent.method,
            WafEvent.primary_signature.label("classifier"),
            WafEvent.response_code.label("rsp_code"),
            WafEvent.severity,
        ).where(
            WafEvent.tenant_id == tenant_id,
            WafEvent.source_ip == source_ip,
            WafEvent.event_time >= start,
            WafEvent.event_time <= end,
        )
        .order_by(desc(WafEvent.event_time))
        .limit(limit)
    ).all()

    bot = db.execute(
        select(
            BotEvent.event_time, BotEvent.action, BotEvent.lb_name,
            BotEvent.endpoint_path.label("endpoint"), BotEvent.method,
            BotEvent.bot_category.label("classifier"),
            BotEvent.confidence_score, BotEvent.challenge_result,
        ).where(
            BotEvent.tenant_id == tenant_id,
            BotEvent.source_ip == source_ip,
            BotEvent.event_time >= start,
            BotEvent.event_time <= end,
        )
        .order_by(desc(BotEvent.event_time))
        .limit(limit)
    ).all()

    timeline: list[dict[str, Any]] = []
    for r in waf:
        timeline.append({
            "event_time": r.event_time,
            "signal": "waf",
            "action": r.action,
            "lb_name": r.lb_name,
            "method": r.method,
            "endpoint": r.endpoint,
            "classifier": r.classifier,
            "rsp_code": r.rsp_code,
            "severity": r.severity,
            "extra": None,
        })
    for r in bot:
        timeline.append({
            "event_time": r.event_time,
            "signal": "bot",
            "action": r.action,
            "lb_name": r.lb_name,
            "method": r.method,
            "endpoint": r.endpoint,
            "classifier": r.classifier,  # bot_category
            "rsp_code": None,
            "severity": None,
            "extra": {
                "confidence_score": r.confidence_score,
                "challenge_result": r.challenge_result,
            },
        })

    timeline.sort(key=lambda r: r["event_time"], reverse=True)
    return timeline[:limit]
