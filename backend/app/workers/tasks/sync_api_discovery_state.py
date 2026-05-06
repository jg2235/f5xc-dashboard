"""Sync per-LB API discovery ML state.

One discovery state per LB. Slow-changing — typical state transitions
are days, not minutes. Polled at config interval (10 min default), not
analytics interval.
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.f5xc.api_transformers import extract_discovery_state
from app.f5xc.client import F5XCClient, F5XCError
from app.logging_config import get_logger
from app.models import ApiDiscoveryState, LoadBalancer
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.sync_api_discovery_state.sync_api_discovery_state"
)
def sync_api_discovery_state() -> dict:
    settings = get_settings()
    if not settings.analytics_enabled:
        log.info("sync_api_discovery_state_skipped_analytics_disabled")
        return {"skipped": True, "reason": "analytics_disabled"}
    total_lbs = 0
    state_counts: dict[str, int] = {}

    with session_scope() as db:
        tenants = iter_tenants(db)
        if not tenants:
            return {"lbs": 0, "states": {}}

        for tenant in tenants:
            lbs = db.execute(
                select(LoadBalancer).where(LoadBalancer.tenant_id == tenant.id)
            ).scalars().all()

            # v0.8.0 — capture sync timestamp BEFORE any upserts.
            from datetime import UTC, datetime as _dt
            sync_started_at = _dt.now(UTC)

            with F5XCClient(
                tenant=tenant.f5xc_tenant,
                api_token=settings.f5xc_api_token or tenant.f5xc_api_token,
                namespace=tenant.f5xc_namespace,
                mock=settings.f5xc_mock,
                timeout=settings.f5xc_request_timeout_seconds,
                max_retries=settings.f5xc_max_retries,
                api_url_template=settings.f5xc_api_url_template,
            ) as client:
                for lb in lbs:
                    try:
                        payload = client.get_api_discovery_state(
                            lb_name=lb.name, namespace=lb.namespace,
                        )
                    except F5XCError as exc:
                        log.warning(
                            "api_discovery_state_error",
                            lb=lb.name, status=exc.status_code,
                        )
                        continue

                    fields = extract_discovery_state(payload)
                    state_counts[fields["state"]] = state_counts.get(fields["state"], 0) + 1

                    stmt = insert(ApiDiscoveryState).values(
                        tenant_id=tenant.id,
                        lb_namespace=lb.namespace,
                        lb_name=lb.name,
                        **fields,
                    )
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_api_discovery_state_lb",
                        set_={
                            "state": stmt.excluded.state,
                            "confidence_score": stmt.excluded.confidence_score,
                            "total_endpoints_discovered": stmt.excluded.total_endpoints_discovered,
                            "total_traffic_samples": stmt.excluded.total_traffic_samples,
                            "last_learning_update": stmt.excluded.last_learning_update,
                            "state_changed_at": stmt.excluded.state_changed_at,
                        },
                    )
                    db.execute(stmt)
                    total_lbs += 1

                    # v0.8.0 — per-LB reap. Discovery state has one row per
                    # LB. If the upsert refreshed THIS LB's row, this reap
                    # is a no-op (updated_at >= sync_started_at). It only
                    # acts on stale combinations from prior runs (e.g.,
                    # an LB renamed/recreated upstream).
                    reaped = db.execute(
                        delete(ApiDiscoveryState).where(
                            ApiDiscoveryState.tenant_id == tenant.id,
                            ApiDiscoveryState.lb_namespace == lb.namespace,
                            ApiDiscoveryState.lb_name == lb.name,
                            ApiDiscoveryState.updated_at < sync_started_at,
                        )
                    ).rowcount or 0
                    if reaped:
                        log.info(
                            "sync_api_discovery_state_reaped_stale",
                            tenant=tenant.name,
                            lb=lb.name,
                            count=reaped,
                        )

    log.info(
        "sync_api_discovery_state_complete",
        lbs=total_lbs, states=state_counts,
    )
    return {"lbs": total_lbs, "states": state_counts}
