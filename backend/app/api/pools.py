"""Origin pool read endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models import HealthCheck, OriginHealth, OriginPool, User
from app.schemas.pool import (
    HealthCheckConfig,
    OriginHealthCell,
    OriginPoolDetail,
    OriginPoolSummary,
    PoolReHealthRow,
    PoolStats,
    ReSiteEntry,
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


_STATUS_PRIORITY = {"unhealthy": 4, "warning": 3, "info": 2, "unknown": 1, "healthy": 0}


def _worst_status(statuses: list[str]) -> str:
    if not statuses:
        return "unknown"
    return max(statuses, key=lambda s: _STATUS_PRIORITY.get(s, 0))  # type: ignore[arg-type]


@router.get("/re-health", response_model=list[PoolReHealthRow], summary="Per-pool RE health summary")
def pool_re_health(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PoolReHealthRow]:
    """Aggregate origin_health rows (site_type='re') per pool, grouped by site.

    Returns one row per pool with a list of RE sites and their aggregate
    health status (worst-of-origins).  Pools with no RE health data return
    an empty re_sites list.
    """
    pools = db.execute(
        select(OriginPool)
        .where(OriginPool.tenant_id == user.tenant_id)
        .order_by(OriginPool.namespace, OriginPool.name)
    ).scalars().all()

    result: list[PoolReHealthRow] = []
    for pool in pools:
        re_rows = db.execute(
            select(OriginHealth)
            .where(
                OriginHealth.pool_id == pool.id,
                OriginHealth.site_type == "re",
            )
            .order_by(OriginHealth.site_name)
        ).scalars().all()

        # Group by site
        sites_map: dict[str, list[OriginHealth]] = {}
        for row in re_rows:
            sites_map.setdefault(row.site_name, []).append(row)

        re_sites: list[ReSiteEntry] = []
        for site_name in sorted(sites_map):
            rows = sites_map[site_name]
            statuses = [r.classified_status for r in rows]
            last_probe = max(
                (r.last_probe_at for r in rows if r.last_probe_at),
                default=None,
            )
            failure_reasons = sorted({
                r.failure_reason for r in rows
                if r.failure_reason and r.classified_status != "healthy"
            })
            re_sites.append(
                ReSiteEntry(
                    site_name=site_name,
                    site_type="re",
                    classified_status=_worst_status(statuses),  # type: ignore[arg-type]
                    healthy_origins=sum(1 for s in statuses if s == "healthy"),
                    total_origins=len(rows),
                    last_probe_at=last_probe,
                    failure_reasons=failure_reasons,
                )
            )

        result.append(
            PoolReHealthRow(
                pool_id=pool.id,
                pool_name=pool.name,
                pool_namespace=pool.namespace,
                re_sites=re_sites,
            )
        )

    return result


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
            failure_reason=r.failure_reason,
            last_status_change=r.last_status_change,
            last_probe_at=r.last_probe_at,
        )
        for r in health_rows
    ]
    site_names = sorted({r.site_name for r in health_rows})

    # Resolve the pool's healthcheck_refs (names) to their synced config
    # objects. Names match within the tenant; the pool's own namespace is
    # tried first, then any namespace (e.g. shared healthchecks).
    refs = pool.healthcheck_refs if isinstance(pool.healthcheck_refs, list) else []
    healthchecks: list[HealthCheckConfig] = []
    if refs:
        hc_rows = db.execute(
            select(HealthCheck).where(
                HealthCheck.tenant_id == user.tenant_id,
                HealthCheck.name.in_(refs),
            )
        ).scalars().all()
        # Prefer a match in the pool's namespace when names collide across ns.
        by_name: dict[str, HealthCheck] = {}
        for hc in hc_rows:
            if hc.name not in by_name or hc.namespace == pool.namespace:
                by_name[hc.name] = hc
        healthchecks = [
            HealthCheckConfig.model_validate(by_name[name])
            for name in refs
            if name in by_name
        ]

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
        healthchecks=healthchecks,
        health_matrix=cells,
        raw_spec=pool.raw_spec,
    )
