"""Bot analytics endpoints (slice 5).

  GET /api/v1/analytics/bot/overview
  GET /api/v1/analytics/bot/sparkline?lb_id=...
  GET /api/v1/analytics/bot/topk?dim=...
  GET /api/v1/analytics/bot/events?...
  GET /api/v1/analytics/bot/endpoints?...

dim ∈ {source_ip, source_country, ua_family, endpoint_path,
       challenge_result, bot_category, action, lb_name, source_asn}

Mirrors the WAF analytics router structure.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, distinct, func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.db import get_db
from app.models import BotEvent, LoadBalancer, User
from sqlalchemy import case
from app.schemas.bot import (
    BotEndpointStats,
    BotEventSummary,
    BotOverviewStats,
    BotSparkline,
    BotSparklinePoint,
    BotTopK,
    BotTopKEntry,
)

router = APIRouter()

BotTopKDim = Literal[
    "source_ip", "source_country", "ua_family",
    "endpoint_path", "challenge_result", "bot_category",
    "action", "lb_name", "source_asn",
]
_DIM_TO_COLUMN = {
    "source_ip": BotEvent.source_ip,
    "source_country": BotEvent.source_country,
    "ua_family": BotEvent.ua_family,
    "endpoint_path": BotEvent.endpoint_path,
    "challenge_result": BotEvent.challenge_result,
    "bot_category": BotEvent.bot_category,
    "action": BotEvent.action,
    "lb_name": BotEvent.lb_name,
    "source_asn": BotEvent.source_asn,
}


def _resolve_lb(db: Session, user: User, lb_id: uuid.UUID | None) -> LoadBalancer | None:
    if lb_id is None:
        return None
    lb = db.get(LoadBalancer, lb_id)
    if lb is None or lb.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Load balancer not found")
    return lb


@router.get("/overview", response_model=BotOverviewStats, summary="Tenant-wide bot overview")
def bot_overview(
    window_minutes: int = Query(default=60, ge=1, le=1440),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BotOverviewStats:
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(minutes=window_minutes)
    row = db.execute(
        select(
            func.coalesce(func.count(), 0).label("req"),
            func.coalesce(func.sum(case((BotEvent.action == "CHALLENGE", 1), else_=0)), 0).label("chal"),
            func.coalesce(func.sum(case((BotEvent.action == "BLOCK", 1), else_=0)), 0).label("blk"),
            func.coalesce(func.sum(case((BotEvent.action == "ALLOW", 1), else_=0)), 0).label("allw"),
        ).where(
            BotEvent.tenant_id == user.tenant_id,
            BotEvent.event_time >= start,
            BotEvent.event_time <= end,
        )
    ).one()
    req, chal, blk, allw = int(row.req), int(row.chal), int(row.blk), int(row.allw)
    chal_rate = round(chal / req * 100.0, 2) if req > 0 else 0.0
    blk_rate = round(blk / req * 100.0, 2) if req > 0 else 0.0
    return BotOverviewStats(
        window_minutes=window_minutes,
        total_requests=req,
        total_challenges=chal,
        total_blocks=blk,
        total_allows=allw,
        challenge_rate_pct=chal_rate,
        block_rate_pct=blk_rate,
    )


@router.get("/sparkline", response_model=BotSparkline, summary="24h @ 5min sparkline")
def bot_sparkline(
    lb_id: uuid.UUID | None = Query(default=None),
    hours: int = Query(default=24, ge=1, le=168),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BotSparkline:
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(hours=hours)
    lb = _resolve_lb(db, user, lb_id)

    bucket_expr = func.to_timestamp(
        func.floor(func.extract("epoch", BotEvent.event_time) / 300) * 300
    ).label("b5")

    stmt = (
        select(
            bucket_expr,
            func.count().label("req"),
            func.sum(case((BotEvent.action == "CHALLENGE", 1), else_=0)).label("chal"),
            func.sum(case((BotEvent.action == "BLOCK", 1), else_=0)).label("blk"),
            func.sum(case((BotEvent.action == "ALLOW", 1), else_=0)).label("allw"),
        )
        .where(
            BotEvent.tenant_id == user.tenant_id,
            BotEvent.event_time >= start,
            BotEvent.event_time <= end,
        )
        .group_by(bucket_expr)
        .order_by(bucket_expr)
    )
    if lb is not None:
        stmt = stmt.where(
            BotEvent.lb_namespace == lb.namespace,
            BotEvent.lb_name == lb.name,
        )

    rows = db.execute(stmt).all()
    points = [
        BotSparklinePoint(
            bucket_time=r.b5,
            request_count=int(r.req or 0),
            challenge_count=int(r.chal or 0),
            block_count=int(r.blk or 0),
            allow_count=int(r.allw or 0),
        )
        for r in rows
    ]
    return BotSparkline(
        lb_namespace=lb.namespace if lb else None,
        lb_name=lb.name if lb else None,
        points=points,
        total_requests=sum(p.request_count for p in points),
        total_challenges=sum(p.challenge_count for p in points),
        total_blocks=sum(p.block_count for p in points),
        total_allows=sum(p.allow_count for p in points),
    )


@router.get("/topk", response_model=BotTopK, summary="Top-K aggregation")
def bot_topk(
    dim: BotTopKDim = Query(default="source_ip"),
    hours: int = Query(default=24, ge=1, le=168),
    action: str | None = Query(default=None, description="Filter to BLOCK | CHALLENGE | ALLOW | MONITOR"),
    bot_category: str | None = Query(default=None),
    lb_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BotTopK:
    settings = get_settings()
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(hours=hours)
    lb = _resolve_lb(db, user, lb_id)

    column = _DIM_TO_COLUMN[dim]
    stmt = (
        select(column.label("key"), func.count().label("cnt"))
        .where(
            BotEvent.tenant_id == user.tenant_id,
            BotEvent.event_time >= start,
            BotEvent.event_time <= end,
            column.is_not(None),
        )
        .group_by(column)
        .order_by(desc("cnt"))
        .limit(settings.bot_topk_size)
    )
    if action:
        stmt = stmt.where(BotEvent.action == action.upper())
    if bot_category:
        stmt = stmt.where(BotEvent.bot_category == bot_category.lower())
    if lb is not None:
        stmt = stmt.where(
            BotEvent.lb_namespace == lb.namespace,
            BotEvent.lb_name == lb.name,
        )

    rows = db.execute(stmt).all()
    return BotTopK(
        dimension=dim,
        entries=[BotTopKEntry(key=str(r.key), count=int(r.cnt)) for r in rows],
    )


@router.get("/events", response_model=list[BotEventSummary], summary="Recent bot events")
def bot_events(
    limit: int = Query(default=200, ge=1, le=2000),
    hours: int = Query(default=24, ge=1, le=168),
    action: str | None = Query(default=None),
    source: str | None = Query(default=None, description="standard | bd_advanced"),
    bot_category: str | None = Query(default=None),
    lb_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BotEventSummary]:
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(hours=hours)
    lb = _resolve_lb(db, user, lb_id)

    stmt = (
        select(BotEvent)
        .where(
            BotEvent.tenant_id == user.tenant_id,
            BotEvent.event_time >= start,
            BotEvent.event_time <= end,
        )
        .order_by(desc(BotEvent.event_time))
        .limit(limit)
    )
    if action:
        stmt = stmt.where(BotEvent.action == action.upper())
    if source:
        stmt = stmt.where(BotEvent.source == source.lower())
    if bot_category:
        stmt = stmt.where(BotEvent.bot_category == bot_category.lower())
    if lb is not None:
        stmt = stmt.where(
            BotEvent.lb_namespace == lb.namespace,
            BotEvent.lb_name == lb.name,
        )

    rows = db.execute(stmt).scalars().all()
    return [
        BotEventSummary(
            event_time=r.event_time,
            lb_namespace=r.lb_namespace,
            lb_name=r.lb_name,
            source=r.source,
            action=r.action,
            bot_category=r.bot_category,
            confidence_bucket=r.confidence_bucket,
            confidence_score=r.confidence_score,
            challenge_result=r.challenge_result,
            challenge_type=r.challenge_type,
            source_ip=r.source_ip,
            source_country=r.source_country,
            source_asn=r.source_asn,
            method=r.method,
            endpoint_path=r.endpoint_path,
            ua_family=r.ua_family,
            user_agent=r.user_agent,
            device_anomalies=r.device_anomalies,
        )
        for r in rows
    ]


@router.get(
    "/endpoints",
    response_model=list[BotEndpointStats],
    summary="Per-endpoint aggregates (slice 5 endpoint breakdown view)",
)
def bot_endpoints(
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=50, ge=1, le=500),
    lb_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BotEndpointStats]:
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(hours=hours)
    lb = _resolve_lb(db, user, lb_id)

    base_filter = [
        BotEvent.tenant_id == user.tenant_id,
        BotEvent.event_time >= start,
        BotEvent.event_time <= end,
        BotEvent.endpoint_path.is_not(None),
    ]
    if lb is not None:
        base_filter.extend([
            BotEvent.lb_namespace == lb.namespace,
            BotEvent.lb_name == lb.name,
        ])

    stmt = (
        select(
            BotEvent.endpoint_path.label("path"),
            BotEvent.method.label("method"),
            func.count().label("total"),
            func.sum(func.case((BotEvent.action == "CHALLENGE", 1), else_=0)).label("chal"),
            func.sum(func.case((BotEvent.action == "BLOCK", 1), else_=0)).label("blk"),
            func.sum(func.case((BotEvent.action == "ALLOW", 1), else_=0)).label("allw"),
            func.sum(func.case((BotEvent.action == "MONITOR", 1), else_=0)).label("mon"),
            func.count(distinct(BotEvent.source_ip)).label("distinct_ips"),
            func.max(BotEvent.event_time).label("last_seen"),
        )
        .where(*base_filter)
        .group_by(BotEvent.endpoint_path, BotEvent.method)
        .order_by(desc("total"))
        .limit(limit)
    )
    rows = db.execute(stmt).all()

    # For each top endpoint, look up the most common bot_category
    out: list[BotEndpointStats] = []
    for r in rows:
        cat_row = db.execute(
            select(BotEvent.bot_category, func.count().label("c"))
            .where(
                *base_filter,
                BotEvent.endpoint_path == r.path,
                BotEvent.method == r.method if r.method is not None else BotEvent.method.is_(None),
            )
            .group_by(BotEvent.bot_category)
            .order_by(desc("c"))
            .limit(1)
        ).first()
        out.append(BotEndpointStats(
            endpoint_path=r.path,
            method=r.method,
            total_events=int(r.total or 0),
            challenge_count=int(r.chal or 0),
            block_count=int(r.blk or 0),
            allow_count=int(r.allw or 0),
            monitor_count=int(r.mon or 0),
            distinct_source_ips=int(r.distinct_ips or 0),
            top_bot_category=cat_row.bot_category if cat_row else None,
            last_seen_at=r.last_seen,
        ))
    return out
