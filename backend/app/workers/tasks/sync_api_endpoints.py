"""Sync discovered API endpoints per LB → api_endpoints table.

For each LB (regardless of has_waf/has_bot — F5 XC's discovery model
runs on any HTTP LB), pull the discovered-endpoints inventory.

Shadow detection: we look up the api_definition objects that the LB
references (via slice 3's policy_attachments table) and compare each
discovered (method, path) tuple against the union of declared endpoints
in those api_definitions. Discovered-but-not-declared = shadow.

Idempotent: upsert by (tenant_id, lb_namespace, lb_name, method, endpoint_path).
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.f5xc.api_transformers import extract_api_endpoint
from app.f5xc.client import F5XCClient, F5XCError
from app.logging_config import get_logger
from app.models import ApiDefinition, ApiEndpoint, LoadBalancer, PolicyAttachment
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


def _declared_endpoints_for_lb(db, tenant_id, lb_id) -> set[tuple[str, str]]:
    """Return (method, path) tuples for endpoints declared in api_definitions
    referenced by this LB.

    Pulls api_definition_ids via PolicyAttachment, then loads each api_def's
    declared_endpoints field (shape: list of {method, path, ...} dicts).
    Returns empty set if nothing declared (everything is shadow).
    """
    api_def_ids = db.execute(
        select(PolicyAttachment.policy_id).where(
            PolicyAttachment.lb_id == lb_id,
            PolicyAttachment.policy_type == "api_definition",
        )
    ).scalars().all()
    if not api_def_ids:
        return set()

    api_defs = db.execute(
        select(ApiDefinition).where(
            ApiDefinition.id.in_(api_def_ids),
            ApiDefinition.tenant_id == tenant_id,
        )
    ).scalars().all()

    declared: set[tuple[str, str]] = set()
    for api_def in api_defs:
        endpoints = api_def.declared_endpoints or []
        if not isinstance(endpoints, list):
            continue
        for ep in endpoints:
            if not isinstance(ep, dict):
                continue
            method = (ep.get("method") or "").upper().strip()
            path = (ep.get("path") or "").strip()
            if method and path:
                declared.add((method, path))
    return declared


@celery_app.task(name="app.workers.tasks.sync_api_endpoints.sync_api_endpoints")
def sync_api_endpoints() -> dict:
    settings = get_settings()
    if not settings.analytics_enabled:
        log.info("sync_api_endpoints_skipped_analytics_disabled")
        return {"skipped": True, "reason": "analytics_disabled"}
    total_endpoints = 0
    total_shadow = 0
    total_lbs = 0

    with session_scope() as db:
        tenants = iter_tenants(db)
        if not tenants:
            return {"endpoints": 0, "shadow": 0, "lbs": 0}

        for tenant in tenants:
            lbs = db.execute(
                select(LoadBalancer).where(LoadBalancer.tenant_id == tenant.id)
            ).scalars().all()

            # v0.8.0 — capture sync timestamp BEFORE any upserts. The
            # ApiEndpoint model's `updated_at` is server-stamped via
            # onupdate=func.now() on every UPDATE, so this gives us a clean
            # boundary for the reap predicate.
            from datetime import UTC
            from datetime import datetime as _dt
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
                        items = client.list_api_endpoints(
                            lb_name=lb.name, namespace=lb.namespace,
                        )
                    except F5XCError as exc:
                        log.warning(
                            "api_endpoints_api_error",
                            lb=lb.name, status=exc.status_code,
                        )
                        continue

                    if len(items) >= settings.api_max_endpoints_per_cycle:
                        log.warning(
                            "api_endpoints_circuit_breaker_hit",
                            lb=lb.name, count=len(items),
                            limit=settings.api_max_endpoints_per_cycle,
                        )

                    declared = _declared_endpoints_for_lb(db, tenant.id, lb.id)

                    for raw in items:
                        fields = extract_api_endpoint(raw, declared_endpoints=declared)
                        if fields is None:
                            continue
                        if fields["is_shadow"]:
                            total_shadow += 1
                        stmt = insert(ApiEndpoint).values(
                            tenant_id=tenant.id,
                            lb_namespace=lb.namespace,
                            lb_name=lb.name,
                            **fields,
                        )
                        # Upsert by unique constraint
                        stmt = stmt.on_conflict_do_update(
                            constraint="uq_api_endpoint_identity",
                            set_={
                                "is_shadow": stmt.excluded.is_shadow,
                                "api_definition_namespace": stmt.excluded.api_definition_namespace,
                                "api_definition_name": stmt.excluded.api_definition_name,
                                "discovery_confidence": stmt.excluded.discovery_confidence,
                                "total_request_samples": stmt.excluded.total_request_samples,
                                "last_seen_at": stmt.excluded.last_seen_at,
                                "first_seen_at": stmt.excluded.first_seen_at,
                                "response_codes": stmt.excluded.response_codes,
                                "query_params": stmt.excluded.query_params,
                                "body_params": stmt.excluded.body_params,
                                "auth_type": stmt.excluded.auth_type,
                            },
                        )
                        db.execute(stmt)
                        total_endpoints += 1

                    total_lbs += 1

                    # v0.8.0 — per-LB reap. Only fires after a successful
                    # iteration of THIS LB's endpoints; LBs that hit the
                    # `continue` above (failed list call) are skipped, so
                    # we never wipe rows we didn't attempt to refresh.
                    reaped = db.execute(
                        delete(ApiEndpoint).where(
                            ApiEndpoint.tenant_id == tenant.id,
                            ApiEndpoint.lb_namespace == lb.namespace,
                            ApiEndpoint.lb_name == lb.name,
                            ApiEndpoint.updated_at < sync_started_at,
                        )
                    ).rowcount or 0
                    if reaped:
                        log.info(
                            "sync_api_endpoints_reaped_stale",
                            tenant=tenant.name,
                            lb=lb.name,
                            count=reaped,
                        )

                    log.debug(
                        "api_endpoints_lb_done",
                        lb=lb.name, count=len(items),
                        reaped=reaped,
                    )

    log.info(
        "sync_api_endpoints_complete",
        endpoints=total_endpoints, shadow=total_shadow, lbs=total_lbs,
    )
    return {"endpoints": total_endpoints, "shadow": total_shadow, "lbs": total_lbs}
