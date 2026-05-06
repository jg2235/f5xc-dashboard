"""WAF analytics endpoints (slice 4).

  GET /api/v1/analytics/waf/overview                → WafOverviewStats (tenant rollup)
  GET /api/v1/analytics/waf/sparkline               → WafSparkline   (tenant total, 24h @ 5min)
  GET /api/v1/analytics/waf/sparkline?lb_id=...     → WafSparkline   (one LB)
  GET /api/v1/analytics/waf/topk?dim=source_ip      → WafTopK
       dim ∈ {source_ip, source_country, primary_signature, url, lb_name, action}
  GET /api/v1/analytics/waf/events?...              → list[WafEventSummary]

Uses the 1-min hypertable for 24h sparklines (288 rows per LB, fast). Top-K and
events query the raw waf_events table.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.db import get_db
from app.models import LoadBalancer, User, WafEvent, WafMetric1Min
from app.schemas.waf import (
    TopKEntry,
    WafEventSummary,
    WafOverviewStats,
    WafSparkline,
    WafSparklinePoint,
    WafTopK,
)

router = APIRouter()

TopKDim = Literal["source_ip", "source_country", "primary_signature", "url", "lb_name", "action"]
_DIM_TO_COLUMN = {
    "source_ip": WafEvent.source_ip,
    "source_country": WafEvent.source_country,
    "primary_signature": WafEvent.primary_signature,
    "url": WafEvent.url,
    "lb_name": WafEvent.lb_name,
    "action": WafEvent.action,
}


def _resolve_lb(db: Session, user: User, lb_id: uuid.UUID | None) -> LoadBalancer | None:
    if lb_id is None:
        return None
    lb = db.get(LoadBalancer, lb_id)
    if lb is None or lb.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Load balancer not found")
    return lb


@router.get("/overview", response_model=WafOverviewStats, summary="Tenant-wide WAF overview")
def waf_overview(
    window_minutes: int = Query(default=60, ge=1, le=1440),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WafOverviewStats:
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(minutes=window_minutes)
    row = db.execute(
        select(
            func.coalesce(func.sum(WafMetric1Min.request_count), 0).label("req"),
            func.coalesce(func.sum(WafMetric1Min.blocked_count), 0).label("blk"),
            func.coalesce(func.sum(WafMetric1Min.monitored_count), 0).label("mon"),
            func.coalesce(func.sum(WafMetric1Min.error_count), 0).label("err"),
        ).where(
            WafMetric1Min.tenant_id == user.tenant_id,
            WafMetric1Min.bucket_time >= start,
            WafMetric1Min.bucket_time <= end,
        )
    ).one()
    req, blk, mon, err = int(row.req), int(row.blk), int(row.mon), int(row.err)
    rate = round(blk / req * 100.0, 2) if req > 0 else 0.0
    return WafOverviewStats(
        window_minutes=window_minutes,
        total_requests=req,
        total_blocked=blk,
        total_monitored=mon,
        total_errors=err,
        block_rate_pct=rate,
    )


@router.get("/sparkline", response_model=WafSparkline, summary="24h @ 5min sparkline")
def waf_sparkline(
    lb_id: uuid.UUID | None = Query(default=None),
    hours: int = Query(default=24, ge=1, le=168),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WafSparkline:
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(hours=hours)

    lb = _resolve_lb(db, user, lb_id)

    # Bucket the 1-min rollups into 5-min windows for the sparkline shape.
    # date_trunc-then-floor: bucket = to_timestamp(floor(extract(epoch)/300)*300).
    bucket_expr = func.to_timestamp(
        func.floor(func.extract("epoch", WafMetric1Min.bucket_time) / 300) * 300
    ).label("b5")

    stmt = (
        select(
            bucket_expr,
            func.sum(WafMetric1Min.request_count).label("req"),
            func.sum(WafMetric1Min.blocked_count).label("blk"),
            func.sum(WafMetric1Min.monitored_count).label("mon"),
            func.sum(WafMetric1Min.error_count).label("err"),
        )
        .where(
            WafMetric1Min.tenant_id == user.tenant_id,
            WafMetric1Min.bucket_time >= start,
            WafMetric1Min.bucket_time <= end,
        )
        .group_by(bucket_expr)
        .order_by(bucket_expr)
    )
    if lb is not None:
        stmt = stmt.where(
            WafMetric1Min.lb_namespace == lb.namespace,
            WafMetric1Min.lb_name == lb.name,
        )

    rows = db.execute(stmt).all()
    points = [
        WafSparklinePoint(
            bucket_time=r.b5,
            request_count=int(r.req or 0),
            blocked_count=int(r.blk or 0),
            monitored_count=int(r.mon or 0),
            error_count=int(r.err or 0),
        )
        for r in rows
    ]
    totals = (
        sum(p.request_count for p in points),
        sum(p.blocked_count for p in points),
        sum(p.monitored_count for p in points),
        sum(p.error_count for p in points),
    )
    return WafSparkline(
        lb_namespace=lb.namespace if lb else None,
        lb_name=lb.name if lb else None,
        points=points,
        total_requests=totals[0],
        total_blocked=totals[1],
        total_monitored=totals[2],
        total_errors=totals[3],
    )


@router.get("/topk", response_model=WafTopK, summary="Top-K aggregation")
def waf_topk(
    dim: TopKDim = Query(default="source_ip"),
    hours: int = Query(default=24, ge=1, le=168),
    action: str | None = Query(default=None, description="Filter to BLOCK | MONITOR | ALLOW"),
    lb_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WafTopK:
    settings = get_settings()
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(hours=hours)
    lb = _resolve_lb(db, user, lb_id)

    column = _DIM_TO_COLUMN[dim]
    stmt = (
        select(column.label("key"), func.count().label("cnt"))
        .where(
            WafEvent.tenant_id == user.tenant_id,
            WafEvent.event_time >= start,
            WafEvent.event_time <= end,
            column.is_not(None),
        )
        .group_by(column)
        .order_by(desc("cnt"))
        .limit(settings.waf_topk_size)
    )
    if action:
        stmt = stmt.where(WafEvent.action == action.upper())
    if lb is not None:
        stmt = stmt.where(
            WafEvent.lb_namespace == lb.namespace,
            WafEvent.lb_name == lb.name,
        )

    rows = db.execute(stmt).all()
    return WafTopK(
        dimension=dim,
        entries=[TopKEntry(key=str(r.key), count=int(r.cnt)) for r in rows],
    )


@router.get("/events", response_model=list[WafEventSummary], summary="Recent WAF events")
def waf_events(
    limit: int = Query(default=200, ge=1, le=2000),
    hours: int = Query(default=24, ge=1, le=168),
    action: str | None = Query(default=None),
    lb_id: uuid.UUID | None = Query(default=None),
    severity: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WafEventSummary]:
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(hours=hours)
    lb = _resolve_lb(db, user, lb_id)

    stmt = (
        select(WafEvent)
        .where(
            WafEvent.tenant_id == user.tenant_id,
            WafEvent.event_time >= start,
            WafEvent.event_time <= end,
        )
        .order_by(desc(WafEvent.event_time))
        .limit(limit)
    )
    if action:
        stmt = stmt.where(WafEvent.action == action.upper())
    if severity:
        stmt = stmt.where(WafEvent.severity == severity.lower())
    if lb is not None:
        stmt = stmt.where(
            WafEvent.lb_namespace == lb.namespace,
            WafEvent.lb_name == lb.name,
        )

    rows = db.execute(stmt).scalars().all()
    return [
        WafEventSummary(
            event_time=r.event_time,
            lb_namespace=r.lb_namespace,
            lb_name=r.lb_name,
            action=r.action,
            source_ip=r.source_ip,
            source_country=r.source_country,
            method=r.method,
            url=r.url,
            response_code=r.response_code,
            primary_signature=r.primary_signature,
            severity=r.severity,
        )
        for r in rows
    ]
