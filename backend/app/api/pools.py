"""Origin pool read endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models import OriginHealth, OriginPool, User
from app.schemas.pool import (
    OriginHealthCell,
    OriginPoolDetail,
    OriginPoolSummary,
    PoolStats,
)

router = APIRouter()


@router.get("", response_model=list[OriginPoolSummary], summary="List origin pools")
def list_pools(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OriginPoolSummary]:
    rows = db.execute(
        select(OriginPool)
        .where(OriginPool.tenant_id == user.tenant_id)
        .order_by(OriginPool.namespace, OriginPool.name)
    ).scalars().all()
    return [OriginPoolSummary.model_validate(r) for r in rows]


@router.get("/stats", response_model=PoolStats, summary="Aggregate pool stats")
def pool_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PoolStats:
    pool_rows = db.execute(
        select(OriginPool).where(OriginPool.tenant_id == user.tenant_id)
    ).scalars().all()

    unhealthy_cells = db.execute(
        select(func.count())
        .select_from(OriginHealth)
        .where(
            OriginHealth.tenant_id == user.tenant_id,
            OriginHealth.classified_status == "unhealthy",
        )
    ).scalar_one()
    warning_cells = db.execute(
        select(func.count())
        .select_from(OriginHealth)
        .where(
            OriginHealth.tenant_id == user.tenant_id,
            OriginHealth.classified_status == "warning",
        )
    ).scalar_one()

    return PoolStats(
        total_pools=len(pool_rows),
        pools_with_unhealthy=sum(1 for p in pool_rows if p.unhealthy_count > 0),
        pools_with_warnings=sum(1 for p in pool_rows if p.warning_count > 0),
        total_origins=sum(p.origin_count for p in pool_rows),
        unhealthy_cells=unhealthy_cells,
        warning_cells=warning_cells,
    )


@router.get("/{pool_id}", response_model=OriginPoolDetail, summary="Pool detail with health matrix")
def get_pool(
    pool_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OriginPoolDetail:
    pool = db.get(OriginPool, pool_id)
    if pool is None or pool.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Origin pool not found")

    health_rows = db.execute(
        select(OriginHealth)
        .where(OriginHealth.pool_id == pool.id)
        .order_by(OriginHealth.origin_address, OriginHealth.site_name)
    ).scalars().all()

    cells = [
        OriginHealthCell(
            origin_address=r.origin_address,
            origin_port=r.origin_port,
            site_name=r.site_name,
            site_type=r.site_type,
            raw_status=r.raw_status,
            classified_status=r.classified_status,  # type: ignore[arg-type]
            consecutive_failures=r.consecutive_failures,
            last_status_change=r.last_status_change,
            last_probe_at=r.last_probe_at,
        )
        for r in health_rows
    ]
    site_names = sorted({r.site_name for r in health_rows})

    return OriginPoolDetail(
        id=pool.id,
        namespace=pool.namespace,
        name=pool.name,
        port=pool.port,
        lb_algorithm=pool.lb_algorithm,
        origin_count=pool.origin_count,
        healthy_count=pool.healthy_count,
        unhealthy_count=pool.unhealthy_count,
        warning_count=pool.warning_count,
        last_healthcheck_at=pool.last_healthcheck_at,
        last_seen_at=pool.last_seen_at,
        origin_addresses=pool.origin_addresses,
        site_names=site_names,
        healthcheck_refs=pool.healthcheck_refs if isinstance(pool.healthcheck_refs, list) else None,
        health_matrix=cells,
        raw_spec=pool.raw_spec,
    )
