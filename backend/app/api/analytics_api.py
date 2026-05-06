"""API analytics endpoints (slice 6).

  GET /api/v1/analytics/api/overview       — tenant rollup (counts, state, error rate, latency)
  GET /api/v1/analytics/api/discovery-state — list per-LB ML state
  GET /api/v1/analytics/api/endpoints       — endpoint inventory with shadow filter + sort
  GET /api/v1/analytics/api/endpoints/{id}  — single endpoint detail with sparkline
  GET /api/v1/analytics/api/topk?dim=...    — top-K (volume / latency / error_rate / shadow / method / auth)

Mirrors WAF / Bot router structure where applicable. Per-endpoint detail
includes the time-series for that endpoint specifically.
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
from app.models import (
    ApiDiscoveryState,
    ApiEndpoint,
    ApiMetric1Min,
    LoadBalancer,
    User,
)
from app.schemas.api_analytics import (
    ApiDiscoveryStateOut,
    ApiEndpointDetail,
    ApiEndpointSparkline,
    ApiEndpointSummary,
    ApiOverviewStats,
    ApiSparklinePoint,
    ApiTopK,
    ApiTopKEntry,
)

router = APIRouter()

ApiTopKDim = Literal[
    "volume",        # top endpoints by request_count
    "latency_p99",   # top endpoints by max p99 latency
    "error_rate",    # top endpoints by 4xx+5xx rate
    "shadow",        # top SHADOW endpoints by volume (operational gold)
    "method",        # HTTP method distribution
    "auth_type",     # authentication-type distribution
]


def _resolve_lb(db: Session, user: User, lb_id: uuid.UUID | None) -> LoadBalancer | None:
    if lb_id is None:
        return None
    lb = db.get(LoadBalancer, lb_id)
    if lb is None or lb.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Load balancer not found")
    return lb


@router.get("/overview", response_model=ApiOverviewStats, summary="Tenant-wide API overview")
def api_overview(
    window_minutes: int = Query(default=60, ge=1, le=1440),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiOverviewStats:
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(minutes=window_minutes)

    # Endpoint counts
    total_endpoints = db.execute(
        select(func.count()).select_from(ApiEndpoint)
        .where(ApiEndpoint.tenant_id == user.tenant_id)
    ).scalar_one()
    shadow_endpoints = db.execute(
        select(func.count()).select_from(ApiEndpoint)
        .where(
            ApiEndpoint.tenant_id == user.tenant_id,
            ApiEndpoint.is_shadow.is_(True),
        )
    ).scalar_one()
    declared_endpoints = total_endpoints - shadow_endpoints

    # Discovery state distribution
    state_rows = db.execute(
        select(ApiDiscoveryState.state, func.count().label("c"))
        .where(ApiDiscoveryState.tenant_id == user.tenant_id)
        .group_by(ApiDiscoveryState.state)
    ).all()
    state_counts = {row.state: int(row.c) for row in state_rows}

    # Latency + error rate from metric hypertable
    metric_row = db.execute(
        select(
            func.coalesce(func.avg(ApiMetric1Min.latency_p99_ms), None).label("avg_p99"),
            func.coalesce(func.sum(ApiMetric1Min.request_count), 0).label("req"),
            func.coalesce(func.sum(ApiMetric1Min.error_4xx_count), 0).label("e4"),
            func.coalesce(func.sum(ApiMetric1Min.error_5xx_count), 0).label("e5"),
        ).where(
            ApiMetric1Min.tenant_id == user.tenant_id,
            ApiMetric1Min.bucket_time >= start,
            ApiMetric1Min.bucket_time <= end,
        )
    ).one()
    req = int(metric_row.req)
    errs = int(metric_row.e4) + int(metric_row.e5)
    err_rate = round(errs / req * 100.0, 2) if req > 0 else 0.0
    avg_p99 = float(metric_row.avg_p99) if metric_row.avg_p99 is not None else None
    if avg_p99 is not None:
        avg_p99 = round(avg_p99, 1)

    return ApiOverviewStats(
        total_endpoints=total_endpoints,
        shadow_endpoints=shadow_endpoints,
        declared_endpoints=declared_endpoints,
        state_counts=state_counts,
        avg_p99_latency_ms=avg_p99,
        error_rate_pct=err_rate,
        window_minutes=window_minutes,
    )


@router.get(
    "/discovery-state",
    response_model=list[ApiDiscoveryStateOut],
    summary="Per-LB ML discovery state",
)
def api_discovery_state(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApiDiscoveryStateOut]:
    rows = db.execute(
        select(ApiDiscoveryState)
        .where(ApiDiscoveryState.tenant_id == user.tenant_id)
        .order_by(ApiDiscoveryState.lb_name)
    ).scalars().all()
    return [
        ApiDiscoveryStateOut(
            lb_namespace=r.lb_namespace,
            lb_name=r.lb_name,
            state=r.state,
            confidence_score=r.confidence_score,
            total_endpoints_discovered=r.total_endpoints_discovered,
            total_traffic_samples=r.total_traffic_samples,
            last_learning_update=r.last_learning_update,
            state_changed_at=r.state_changed_at,
        )
        for r in rows
    ]


@router.get(
    "/endpoints",
    response_model=list[ApiEndpointSummary],
    summary="Discovered endpoint inventory",
)
def api_endpoints(
    limit: int = Query(default=100, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    shadow_only: bool = Query(default=False),
    lb_id: uuid.UUID | None = Query(default=None),
    auth_type: str | None = Query(default=None),
    sort: Literal["volume", "last_seen", "method", "path"] = Query(default="volume"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApiEndpointSummary]:
    lb = _resolve_lb(db, user, lb_id)
    stmt = select(ApiEndpoint).where(ApiEndpoint.tenant_id == user.tenant_id)
    if shadow_only:
        stmt = stmt.where(ApiEndpoint.is_shadow.is_(True))
    if lb is not None:
        stmt = stmt.where(
            ApiEndpoint.lb_namespace == lb.namespace,
            ApiEndpoint.lb_name == lb.name,
        )
    if auth_type:
        stmt = stmt.where(ApiEndpoint.auth_type == auth_type.lower())

    if sort == "volume":
        stmt = stmt.order_by(desc(ApiEndpoint.total_request_samples))
    elif sort == "last_seen":
        stmt = stmt.order_by(desc(ApiEndpoint.last_seen_at))
    elif sort == "method":
        stmt = stmt.order_by(ApiEndpoint.method, ApiEndpoint.endpoint_path)
    else:
        stmt = stmt.order_by(ApiEndpoint.endpoint_path)

    stmt = stmt.limit(limit).offset(offset)
    rows = db.execute(stmt).scalars().all()
    return [
        ApiEndpointSummary(
            id=str(r.id),
            lb_namespace=r.lb_namespace,
            lb_name=r.lb_name,
            method=r.method,
            endpoint_path=r.endpoint_path,
            is_shadow=r.is_shadow,
            api_definition_namespace=r.api_definition_namespace,
            api_definition_name=r.api_definition_name,
            discovery_confidence=r.discovery_confidence,
            total_request_samples=r.total_request_samples,
            last_seen_at=r.last_seen_at,
            auth_type=r.auth_type,
            response_codes=r.response_codes,
        )
        for r in rows
    ]


@router.get(
    "/endpoints/{endpoint_id}",
    response_model=ApiEndpointDetail,
    summary="Single endpoint detail with inferred shape",
)
def api_endpoint_detail(
    endpoint_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiEndpointDetail:
    r = db.get(ApiEndpoint, endpoint_id)
    if r is None or r.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return ApiEndpointDetail(
        id=str(r.id),
        lb_namespace=r.lb_namespace,
        lb_name=r.lb_name,
        method=r.method,
        endpoint_path=r.endpoint_path,
        is_shadow=r.is_shadow,
        api_definition_namespace=r.api_definition_namespace,
        api_definition_name=r.api_definition_name,
        discovery_confidence=r.discovery_confidence,
        total_request_samples=r.total_request_samples,
        last_seen_at=r.last_seen_at,
        first_seen_at=r.first_seen_at,
        auth_type=r.auth_type,
        response_codes=r.response_codes,
        query_params=r.query_params,
        body_params=r.body_params,
    )


@router.get(
    "/endpoints/{endpoint_id}/sparkline",
    response_model=ApiEndpointSparkline,
    summary="Time-series for one endpoint",
)
def api_endpoint_sparkline(
    endpoint_id: uuid.UUID,
    hours: int = Query(default=24, ge=1, le=168),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiEndpointSparkline:
    ep = db.get(ApiEndpoint, endpoint_id)
    if ep is None or ep.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Endpoint not found")

    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(hours=hours)

    bucket_expr = func.to_timestamp(
        func.floor(func.extract("epoch", ApiMetric1Min.bucket_time) / 300) * 300
    ).label("b5")

    rows = db.execute(
        select(
            bucket_expr,
            func.sum(ApiMetric1Min.request_count).label("req"),
            func.sum(ApiMetric1Min.error_4xx_count).label("e4"),
            func.sum(ApiMetric1Min.error_5xx_count).label("e5"),
            func.avg(ApiMetric1Min.latency_p50_ms).label("p50"),
            func.max(ApiMetric1Min.latency_p95_ms).label("p95"),
            func.max(ApiMetric1Min.latency_p99_ms).label("p99"),
        )
        .where(
            ApiMetric1Min.tenant_id == user.tenant_id,
            ApiMetric1Min.lb_namespace == ep.lb_namespace,
            ApiMetric1Min.lb_name == ep.lb_name,
            ApiMetric1Min.method == ep.method,
            ApiMetric1Min.endpoint_path == ep.endpoint_path,
            ApiMetric1Min.bucket_time >= start,
            ApiMetric1Min.bucket_time <= end,
        )
        .group_by(bucket_expr)
        .order_by(bucket_expr)
    ).all()

    points = [
        ApiSparklinePoint(
            bucket_time=r.b5,
            request_count=int(r.req or 0),
            error_4xx_count=int(r.e4 or 0),
            error_5xx_count=int(r.e5 or 0),
            latency_p50_ms=round(float(r.p50), 1) if r.p50 is not None else None,
            latency_p95_ms=round(float(r.p95), 1) if r.p95 is not None else None,
            latency_p99_ms=round(float(r.p99), 1) if r.p99 is not None else None,
        )
        for r in rows
    ]
    p99_max = max((p.latency_p99_ms for p in points if p.latency_p99_ms is not None), default=None)
    return ApiEndpointSparkline(
        method=ep.method,
        endpoint_path=ep.endpoint_path,
        points=points,
        total_requests=sum(p.request_count for p in points),
        total_4xx=sum(p.error_4xx_count for p in points),
        total_5xx=sum(p.error_5xx_count for p in points),
        max_p99_ms=p99_max,
    )


@router.get("/topk", response_model=ApiTopK, summary="API top-K aggregation")
def api_topk(
    dim: ApiTopKDim = Query(default="volume"),
    hours: int = Query(default=24, ge=1, le=168),
    lb_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiTopK:
    settings = get_settings()
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(hours=hours)
    lb = _resolve_lb(db, user, lb_id)

    if dim in {"method", "auth_type"}:
        # Aggregate over endpoint inventory, not metrics
        col = ApiEndpoint.method if dim == "method" else ApiEndpoint.auth_type
        stmt = (
            select(col.label("key"), func.count().label("cnt"))
            .where(ApiEndpoint.tenant_id == user.tenant_id, col.is_not(None))
            .group_by(col)
            .order_by(desc("cnt"))
            .limit(settings.api_topk_size)
        )
        if lb is not None:
            stmt = stmt.where(
                ApiEndpoint.lb_namespace == lb.namespace,
                ApiEndpoint.lb_name == lb.name,
            )
        rows = db.execute(stmt).all()
        return ApiTopK(
            dimension=dim,
            entries=[ApiTopKEntry(key=str(r.key), count=int(r.cnt)) for r in rows],
        )

    if dim == "shadow":
        # Top shadow endpoints by request volume (the operator gold widget)
        stmt = (
            select(
                ApiEndpoint.method,
                ApiEndpoint.endpoint_path,
                ApiEndpoint.total_request_samples.label("samples"),
            )
            .where(
                ApiEndpoint.tenant_id == user.tenant_id,
                ApiEndpoint.is_shadow.is_(True),
            )
            .order_by(desc(ApiEndpoint.total_request_samples))
            .limit(settings.api_topk_size)
        )
        if lb is not None:
            stmt = stmt.where(
                ApiEndpoint.lb_namespace == lb.namespace,
                ApiEndpoint.lb_name == lb.name,
            )
        rows = db.execute(stmt).all()
        return ApiTopK(
            dimension=dim,
            entries=[
                ApiTopKEntry(key=f"{r.method} {r.endpoint_path}", count=int(r.samples or 0))
                for r in rows
            ],
        )

    # Time-series-based dimensions: volume, latency_p99, error_rate
    base_filter = [
        ApiMetric1Min.tenant_id == user.tenant_id,
        ApiMetric1Min.bucket_time >= start,
        ApiMetric1Min.bucket_time <= end,
    ]
    if lb is not None:
        base_filter.extend([
            ApiMetric1Min.lb_namespace == lb.namespace,
            ApiMetric1Min.lb_name == lb.name,
        ])

    if dim == "volume":
        stmt = (
            select(
                ApiMetric1Min.method,
                ApiMetric1Min.endpoint_path,
                func.sum(ApiMetric1Min.request_count).label("v"),
            )
            .where(*base_filter)
            .group_by(ApiMetric1Min.method, ApiMetric1Min.endpoint_path)
            .order_by(desc("v"))
            .limit(settings.api_topk_size)
        )
    elif dim == "latency_p99":
        stmt = (
            select(
                ApiMetric1Min.method,
                ApiMetric1Min.endpoint_path,
                func.max(ApiMetric1Min.latency_p99_ms).label("v"),
            )
            .where(*base_filter, ApiMetric1Min.latency_p99_ms.is_not(None))
            .group_by(ApiMetric1Min.method, ApiMetric1Min.endpoint_path)
            .order_by(desc("v"))
            .limit(settings.api_topk_size)
        )
    else:  # error_rate — at least 100 requests to avoid noise from low-traffic endpoints
        stmt = (
            select(
                ApiMetric1Min.method,
                ApiMetric1Min.endpoint_path,
                (
                    func.sum(
                        ApiMetric1Min.error_4xx_count + ApiMetric1Min.error_5xx_count
                    ) * 1000
                    / func.greatest(func.sum(ApiMetric1Min.request_count), 1)
                ).label("v"),
                func.sum(ApiMetric1Min.request_count).label("req"),
            )
            .where(*base_filter)
            .group_by(ApiMetric1Min.method, ApiMetric1Min.endpoint_path)
            .having(func.sum(ApiMetric1Min.request_count) >= 100)
            .order_by(desc("v"))
            .limit(settings.api_topk_size)
        )

    rows = db.execute(stmt).all()
    return ApiTopK(
        dimension=dim,
        entries=[
            ApiTopKEntry(
                key=f"{r.method} {r.endpoint_path}",
                # For latency_p99 we store ms as int; for error_rate we store rate * 1000
                # (per-mille) so the bar widget can display proportional bars
                count=int(r.v or 0),
            )
            for r in rows
        ],
    )
