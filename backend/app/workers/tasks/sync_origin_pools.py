"""Sync origin_pools from F5 XC → DB.

v0.9.0: iterates tenant.effective_namespaces. Per-namespace list call,
per-pool detail GET. Reaping scoped to successfully-listed namespaces only
(failures don't reap, preventing transient errors from wiping cache).
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.f5xc.client import F5XCClient
from app.f5xc.transformers import extract_pool_fields
from app.logging_config import get_logger
from app.models import OriginPool
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.sync_origin_pools.sync_origin_pools")
def sync_origin_pools() -> dict:
    settings = get_settings()
    total = 0
    with session_scope() as db:
        tenants = iter_tenants(db)
        if not tenants:
            return {"tenants": 0, "origin_pools": 0}

        for tenant in tenants:
            namespaces = tenant.effective_namespaces
            sync_started_at = datetime.now(UTC)
            successful_namespaces: list[str] = []
            tenant_total = 0

            with F5XCClient(
                tenant=tenant.f5xc_tenant,
                api_token=settings.f5xc_api_token or tenant.f5xc_api_token,
                namespace=tenant.f5xc_namespace,  # default; per-call overrides below
                mock=settings.f5xc_mock,
                timeout=settings.f5xc_request_timeout_seconds,
                max_retries=settings.f5xc_max_retries,
                api_url_template=settings.f5xc_api_url_template,
            ) as client:
                for namespace in namespaces:
                    try:
                        listed = client.list_origin_pools(namespace=namespace)
                    except Exception as exc:
                        log.warning(
                            "sync_origin_pools_list_failed",
                            tenant=tenant.name, namespace=namespace, error=str(exc),
                        )
                        continue

                    # Per-pool detail GET — list returns metadata only.
                    items = []
                    for stub in listed:
                        name = stub.get("name", "")
                        ns = stub.get("namespace") or namespace
                        if not name:
                            continue
                        try:
                            detail = client.get_origin_pool(name=name, namespace=ns)
                        except Exception as e:
                            log.warning(
                                "origin_pool_detail_fetch_failed",
                                name=name, namespace=ns, error=str(e),
                            )
                            continue
                        items.append({
                            **stub,
                            "spec": detail.get("spec") or detail.get("get_spec") or {},
                        })

                    for item in items:
                        fields = extract_pool_fields(item)
                        stmt = insert(OriginPool).values(
                            tenant_id=tenant.id,
                            namespace=fields["namespace"] or namespace,
                            name=fields["name"],
                            port=fields["port"],
                            lb_algorithm=fields["lb_algorithm"],
                            origin_count=fields["origin_count"],
                            origin_addresses=fields["origin_addresses"],
                            healthcheck_refs=fields["healthcheck_refs"],
                            raw_spec=fields["raw_spec"],
                            last_seen_at=sync_started_at,
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["tenant_id", "namespace", "name"],
                            set_={
                                "port": stmt.excluded.port,
                                "lb_algorithm": stmt.excluded.lb_algorithm,
                                "origin_count": stmt.excluded.origin_count,
                                "origin_addresses": stmt.excluded.origin_addresses,
                                "healthcheck_refs": stmt.excluded.healthcheck_refs,
                                "raw_spec": stmt.excluded.raw_spec,
                                "last_seen_at": stmt.excluded.last_seen_at,
                            },
                        )
                        db.execute(stmt)
                        tenant_total += 1
                        total += 1

                    successful_namespaces.append(namespace)
                    log.info(
                        "sync_origin_pools_namespace_done",
                        tenant=tenant.name, namespace=namespace, count=len(items),
                    )

            # v0.8.0 — stale-row reaping; v0.9.0 — scoped to successfully-listed
            # namespaces only. Cascade rules drop dependent origin_health rows.
            reaped = 0
            if successful_namespaces:
                reaped = db.execute(
                    delete(OriginPool).where(
                        OriginPool.tenant_id == tenant.id,
                        OriginPool.namespace.in_(successful_namespaces),
                        OriginPool.last_seen_at < sync_started_at,
                    )
                ).rowcount or 0
                if reaped:
                    log.info(
                        "sync_origin_pools_reaped_stale",
                        tenant=tenant.name,
                        namespaces=successful_namespaces,
                        count=reaped,
                    )

            log.info(
                "sync_origin_pools_tenant_done",
                tenant=tenant.name,
                namespaces=successful_namespaces,
                count=tenant_total,
                reaped=reaped,
            )
    return {"origin_pools": total}
