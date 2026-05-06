"""Security analytics endpoints (slice 7).

  GET /api/v1/analytics/security/overview      — tenant cross-signal summary
  GET /api/v1/analytics/security/geo           — country-level event counts (choropleth)
  GET /api/v1/analytics/security/attackers     — attacker profiles (sortable, filterable)
  GET /api/v1/analytics/security/attackers/{ip}/timeline  — chronological event log
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.db import get_db
from app.models import Alert, AttackerProfile, BotEvent, User, WafEvent
from app.schemas.security import (
    AttackerProfileSummary,
    AttackerTimelineEntry,
    GeoEntry,
    SecurityOverviewStats,
)
from app.security.correlator import attacker_timeline as build_timeline

router = APIRouter()


@router.get(
    "/overview",
    response_model=SecurityOverviewStats,
    summary="Tenant-wide cross-signal threat summary",
)
def security_overview(
    window_minutes: int = Query(default=1440, ge=1, le=10080),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SecurityOverviewStats:
    end = datetime.now(UTC)
    start = end - timedelta(minutes=window_minutes)

    # Attacker count
    attacker_row = db.execute(
        select(
            func.count().label("attackers"),
            func.count(func.distinct(AttackerProfile.source_country)).label("countries"),
        ).where(AttackerProfile.tenant_id == user.tenant_id)
    ).one()

    # Top country (from waf+bot events in window — more accurate than profiles which span longer)
    waf_country_row = db.execute(
        select(WafEvent.source_country, func.count().label("c"))
        .where(
            WafEvent.tenant_id == user.tenant_id,
            WafEvent.event_time >= start,
            WafEvent.action.in_(("BLOCK", "MONITOR")),
            WafEvent.source_country.is_not(None),
        )
        .group_by(WafEvent.source_country)
        .order_by(desc("c"))
        .limit(1)
    ).first()
    top_country = waf_country_row.source_country if waf_country_row else None
    top_country_count = int(waf_country_row.c) if waf_country_row else 0

    # WAF blocks
    waf_blocks = db.execute(
        select(func.count()).select_from(WafEvent).where(
            WafEvent.tenant_id == user.tenant_id,
            WafEvent.event_time >= start,
            WafEvent.action == "BLOCK",
        )
    ).scalar_one()

    # Bot interventions (block + challenge)
    bot_interventions = db.execute(
        select(func.count()).select_from(BotEvent).where(
            BotEvent.tenant_id == user.tenant_id,
            BotEvent.event_time >= start,
            BotEvent.action.in_(("BLOCK", "CHALLENGE")),
        )
    ).scalar_one()

    # API 4xx (approximated from waf events with 4xx response code)
    api_4xx = db.execute(
        select(func.count()).select_from(WafEvent).where(
            WafEvent.tenant_id == user.tenant_id,
            WafEvent.event_time >= start,
            WafEvent.response_code.between(400, 499),
        )
    ).scalar_one()

    # Alert counts
    open_alerts = db.execute(
        select(func.count()).select_from(Alert).where(
            Alert.tenant_id == user.tenant_id,
            Alert.status == "open",
        )
    ).scalar_one()
    critical_alerts = db.execute(
        select(func.count()).select_from(Alert).where(
            Alert.tenant_id == user.tenant_id,
            Alert.status == "open",
            Alert.severity == "critical",
        )
    ).scalar_one()

    return SecurityOverviewStats(
        window_minutes=window_minutes,
        total_attackers=int(attacker_row.attackers),
        countries_seen=int(attacker_row.countries),
        top_country=top_country,
        top_country_count=top_country_count,
        total_waf_blocks=int(waf_blocks),
        total_bot_interventions=int(bot_interventions),
        total_api_4xx=int(api_4xx),
        open_alerts=int(open_alerts),
        critical_alerts=int(critical_alerts),
    )


@router.get(
    "/geo",
    response_model=list[GeoEntry],
    summary="Country-level event counts (for choropleth)",
)
def security_geo(
    hours: int = Query(default=24, ge=1, le=168),
    signal: Literal["all", "waf", "bot"] = Query(default="all"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[GeoEntry]:
    start = datetime.now(UTC) - timedelta(hours=hours)
    out: dict[str, int] = {}

    if signal in ("all", "waf"):
        rows = db.execute(
            select(WafEvent.source_country, func.count().label("c"))
            .where(
                WafEvent.tenant_id == user.tenant_id,
                WafEvent.event_time >= start,
                WafEvent.action.in_(("BLOCK", "MONITOR")),
                WafEvent.source_country.is_not(None),
            )
            .group_by(WafEvent.source_country)
        ).all()
        for r in rows:
            out[r.source_country] = out.get(r.source_country, 0) + int(r.c)

    if signal in ("all", "bot"):
        rows = db.execute(
            select(BotEvent.source_country, func.count().label("c"))
            .where(
                BotEvent.tenant_id == user.tenant_id,
                BotEvent.event_time >= start,
                BotEvent.action.in_(("BLOCK", "CHALLENGE", "MONITOR")),
                BotEvent.source_country.is_not(None),
            )
            .group_by(BotEvent.source_country)
        ).all()
        for r in rows:
            out[r.source_country] = out.get(r.source_country, 0) + int(r.c)

    return [
        GeoEntry(country=country, count=count)
        for country, count in sorted(out.items(), key=lambda kv: kv[1], reverse=True)
    ]


@router.get(
    "/attackers",
    response_model=list[AttackerProfileSummary],
    summary="Cross-signal attacker profiles",
)
def list_attackers(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    country: str | None = Query(default=None),
    sort: Literal["total", "waf", "bot", "last_seen"] = Query(default="total"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AttackerProfileSummary]:
    settings = get_settings()
    stmt = select(AttackerProfile).where(AttackerProfile.tenant_id == user.tenant_id)
    if country:
        stmt = stmt.where(AttackerProfile.source_country == country.upper())

    sort_map = {
        "total": desc(AttackerProfile.total_events),
        "waf": desc(
            AttackerProfile.waf_block_count + AttackerProfile.waf_monitor_count
        ),
        "bot": desc(
            AttackerProfile.bot_block_count + AttackerProfile.bot_challenge_count
        ),
        "last_seen": desc(AttackerProfile.last_seen_at),
    }
    stmt = stmt.order_by(sort_map[sort])
    stmt = stmt.limit(min(limit, settings.security_topk_size * 50)).offset(offset)

    rows = db.execute(stmt).scalars().all()
    return [
        AttackerProfileSummary(
            id=str(r.id),
            source_ip=r.source_ip,
            source_asn=r.source_asn,
            source_country=r.source_country,
            waf_block_count=r.waf_block_count,
            waf_monitor_count=r.waf_monitor_count,
            bot_block_count=r.bot_block_count,
            bot_challenge_count=r.bot_challenge_count,
            api_4xx_count=r.api_4xx_count,
            total_events=r.total_events,
            top_endpoint=r.top_endpoint,
            top_signature=r.top_signature,
            distinct_lbs=r.distinct_lbs,
            first_seen_at=r.first_seen_at,
            last_seen_at=r.last_seen_at,
        )
        for r in rows
    ]


@router.get(
    "/attackers/{source_ip}/timeline",
    response_model=list[AttackerTimelineEntry],
    summary="Per-attacker chronological event timeline",
)
def attacker_timeline(
    source_ip: str,
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=200, ge=1, le=2000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AttackerTimelineEntry]:
    timeline = build_timeline(
        db,
        tenant_id=user.tenant_id,
        source_ip=source_ip,
        window=timedelta(hours=hours),
        limit=limit,
    )
    return [AttackerTimelineEntry(**t) for t in timeline]
