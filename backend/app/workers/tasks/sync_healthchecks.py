"""Sync per-origin per-site health from F5 XC → DB.

Algorithm:
  1. For each tenant, build a {pool_name -> set(site_names)} map by
     iterating LoadBalancers, taking each LB's origin_pool_refs and
     advertised_sites, then expanding ALL_RE_SITES_SENTINEL against the
     cached Site table (RE sites only) and "virtual:<name>" against
     the matching virtual_site if its selector resolves.
  2. For each (pool, site) combo, call F5XC GET origin health.
  3. Upsert OriginHealth rows on (pool_id, origin_address, origin_port, site_name).
  4. Roll up healthy/unhealthy/warning counts onto the parent OriginPool.
  5. Honor circuit breaker (HEALTHCHECK_MAX_CALLS_PER_CYCLE) and pacing
     (HEALTHCHECK_PER_REQUEST_DELAY_MS).

Fail behavior: an exception on a single (pool, site) call is logged but
does not abort the whole cycle — other combos still get refreshed. This
matches operational expectations (one bad RE shouldn't blind the dashboard).
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.f5xc.client import F5XCClient, F5XCError
from app.f5xc.transformers import ALL_RE_SITES_SENTINEL, classify_origin_status
from app.logging_config import get_logger
from app.models import LoadBalancer, OriginHealth, OriginPool, Site, Tenant
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


def _resolve_site_targets(db: Session, tenant: Tenant, advertised: list[str]) -> set[str]:
    """Expand sentinels to concrete site names.

    - ALL_RE_SITES_SENTINEL → every site of type "re"
    - "virtual:<name>" → expand against virtual site selector (slice 2: log-only,
      virtual sites resolve at the LB-advertise layer, not via API directly).
      For now, treat virtual sites as opaque: pass the bare name through.
    - Bare name → as-is.
    """
    if not advertised:
        return set()
    out: set[str] = set()
    expanded_re = False
    for ref in advertised:
        if ref == ALL_RE_SITES_SENTINEL:
            if not expanded_re:
                re_sites = db.execute(
                    select(Site.name).where(
                        Site.tenant_id == tenant.id, Site.site_type == "re"
                    )
                ).scalars().all()
                out.update(re_sites)
                expanded_re = True
        elif ref.startswith("virtual:"):
            # Virtual site expansion is non-trivial; for v1 use the virtual site
            # name itself as a targeting label — F5 XC accepts it on the health
            # endpoint. Production refinement deferred.
            out.add(ref.split(":", 1)[1])
        else:
            out.add(ref)
    return out


def _build_pool_site_map(db: Session, tenant: Tenant) -> dict[str, set[str]]:
    """Per pool name → set of site names where it should be probed."""
    lbs = db.execute(
        select(LoadBalancer).where(LoadBalancer.tenant_id == tenant.id)
    ).scalars().all()

    out: dict[str, set[str]] = defaultdict(set)
    for lb in lbs:
        sites = _resolve_site_targets(db, tenant, lb.advertised_sites)
        for pool_name in lb.origin_pool_refs:
            out[pool_name].update(sites)
    return out


def _upsert_origin_health(
    db: Session,
    *,
    tenant_id,
    pool: OriginPool,
    site_name: str,
    site_type: str | None,
    item: dict[str, Any],
    now: datetime,
) -> str:
    """Returns the classified status."""
    raw_status = (item.get("status") or "UNKNOWN").upper()
    classified = classify_origin_status(raw_status)
    last_change_str = item.get("last_status_change")
    last_probe_str = item.get("last_probe")

    def _maybe_iso(s: str | None) -> datetime | None:
        if not s:
            return None
        s2 = s[:-1] + "+00:00" if s.endswith("Z") else s
        try:
            dt = datetime.fromisoformat(s2)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return None

    stmt = insert(OriginHealth).values(
        tenant_id=tenant_id,
        pool_id=pool.id,
        origin_address=str(item.get("address", "")),
        origin_port=item.get("port"),
        site_name=site_name,
        site_type=site_type,
        raw_status=raw_status,
        classified_status=classified,
        consecutive_failures=int(item.get("consecutive_failures") or 0),
        last_status_change=_maybe_iso(last_change_str),
        last_probe_at=_maybe_iso(last_probe_str),
        last_seen_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["pool_id", "origin_address", "origin_port", "site_name"],
        set_={
            "site_type": stmt.excluded.site_type,
            "raw_status": stmt.excluded.raw_status,
            "classified_status": stmt.excluded.classified_status,
            "consecutive_failures": stmt.excluded.consecutive_failures,
            "last_status_change": stmt.excluded.last_status_change,
            "last_probe_at": stmt.excluded.last_probe_at,
            "last_seen_at": stmt.excluded.last_seen_at,
        },
    )
    db.execute(stmt)
    return classified


def _rollup_pool(db: Session, pool: OriginPool, now: datetime) -> None:
    """Update healthy/unhealthy/warning counts on the pool from current OriginHealth rows."""
    rows = db.execute(
        select(OriginHealth.classified_status).where(OriginHealth.pool_id == pool.id)
    ).scalars().all()
    healthy = sum(1 for s in rows if s == "healthy")
    unhealthy = sum(1 for s in rows if s == "unhealthy")
    warning = sum(1 for s in rows if s == "warning")
    pool.healthy_count = healthy
    pool.unhealthy_count = unhealthy
    pool.warning_count = warning
    pool.last_healthcheck_at = now


@celery_app.task(name="app.workers.tasks.sync_healthchecks.sync_healthchecks")
def sync_healthchecks() -> dict:
    settings = get_settings()
    if not settings.analytics_enabled:
        log.info("sync_healthchecks_skipped_analytics_disabled")
        return {"skipped": True, "reason": "analytics_disabled"}
    delay = settings.healthcheck_per_request_delay_ms / 1000.0
    budget = settings.healthcheck_max_calls_per_cycle

    calls_made = 0
    rows_upserted = 0
    pools_rolled_up = 0
    skipped_for_budget = 0
    errors = 0

    with session_scope() as db:
        tenants = iter_tenants(db)
        if not tenants:
            return {"tenants": 0, "calls": 0, "rows": 0}

        # Build a name→Site lookup once per tenant for site_type tagging.
        for tenant in tenants:
            sites_by_name = {
                s.name: s
                for s in db.execute(
                    select(Site).where(Site.tenant_id == tenant.id)
                ).scalars().all()
            }
            pools_by_name = {
                p.name: p
                for p in db.execute(
                    select(OriginPool).where(OriginPool.tenant_id == tenant.id)
                ).scalars().all()
            }

            pool_site_map = _build_pool_site_map(db, tenant)

            with F5XCClient(
                tenant=tenant.f5xc_tenant,
                api_token=settings.f5xc_api_token or tenant.f5xc_api_token,
                namespace=tenant.f5xc_namespace,
                mock=settings.f5xc_mock,
                timeout=settings.f5xc_request_timeout_seconds,
                max_retries=settings.f5xc_max_retries,
                api_url_template=settings.f5xc_api_url_template,
            ) as client:
                now = datetime.now(UTC)
                touched_pools: set[str] = set()

                for pool_name, sites in pool_site_map.items():
                    pool = pools_by_name.get(pool_name)
                    if pool is None:
                        log.debug("healthcheck_skip_unknown_pool", pool=pool_name)
                        continue

                    for site_name in sorted(sites):
                        if calls_made >= budget:
                            skipped_for_budget += 1
                            continue
                        try:
                            payload = client.get_origin_health(
                                pool_name=pool.name,
                                site_name=site_name,
                                namespace=pool.namespace,
                            )
                        except F5XCError as exc:
                            errors += 1
                            log.warning(
                                "healthcheck_api_error",
                                pool=pool.name,
                                site=site_name,
                                status=exc.status_code,
                            )
                            calls_made += 1
                            if delay:
                                time.sleep(delay)
                            continue

                        calls_made += 1
                        site_obj = sites_by_name.get(site_name)
                        site_type = site_obj.site_type if site_obj else None

                        for item in payload.get("items", []):
                            _upsert_origin_health(
                                db,
                                tenant_id=tenant.id,
                                pool=pool,
                                site_name=site_name,
                                site_type=site_type,
                                item=item,
                                now=now,
                            )
                            rows_upserted += 1

                        touched_pools.add(pool.name)
                        if delay:
                            time.sleep(delay)

                # Roll up only the pools we successfully touched
                for pool_name in touched_pools:
                    pool = pools_by_name.get(pool_name)
                    if pool is not None:
                        _rollup_pool(db, pool, now)
                        pools_rolled_up += 1

    log.info(
        "sync_healthchecks_complete",
        calls=calls_made,
        rows=rows_upserted,
        pools=pools_rolled_up,
        skipped_for_budget=skipped_for_budget,
        errors=errors,
    )
    return {
        "calls": calls_made,
        "rows": rows_upserted,
        "pools_rolled_up": pools_rolled_up,
        "skipped_for_budget": skipped_for_budget,
        "errors": errors,
    }
