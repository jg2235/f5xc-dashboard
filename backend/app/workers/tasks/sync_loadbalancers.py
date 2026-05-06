"""Sync HTTP Load Balancers from F5 XC → DB.

v0.9.0: iterates tenant.effective_namespaces — one or many namespaces
configured per tenant. The list call is per-namespace; per-LB GETs use
the namespace returned in the stub.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.f5xc.client import F5XCClient
from app.f5xc.transformers import extract_lb_fields
from app.logging_config import get_logger
from app.models import LoadBalancer
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.sync_loadbalancers.sync_loadbalancers")
def sync_loadbalancers() -> dict:
    settings = get_settings()
    total = 0
    with session_scope() as db:
        tenants = iter_tenants(db)
        if not tenants:
            log.warning("sync_loadbalancers_no_tenants")
            return {"tenants": 0, "load_balancers": 0}

        for tenant in tenants:
            namespaces = tenant.effective_namespaces
            sync_started_at = datetime.now(UTC)
            successful_namespaces: list[str] = []
            tenant_total = 0

            with F5XCClient(
                tenant=tenant.f5xc_tenant,
                api_token=settings.f5xc_api_token or tenant.f5xc_api_token,
                namespace=tenant.f5xc_namespace,  # default, individual calls override
                mock=settings.f5xc_mock,
                timeout=settings.f5xc_request_timeout_seconds,
                max_retries=settings.f5xc_max_retries,
                api_url_template=settings.f5xc_api_url_template,
            ) as client:
                for namespace in namespaces:
                    try:
                        listed = client.list_http_load_balancers(namespace=namespace)
                    except Exception as exc:
                        log.warning(
                            "sync_loadbalancers_list_failed",
                            tenant=tenant.name, namespace=namespace, error=str(exc),
                        )
                        continue

                    # F5 XC list responses return metadata only with get_spec=null.
                    # Per-item GET is required to materialize the spec body.
                    items = []
                    for stub in listed:
                        name = stub.get("name", "")
                        ns = stub.get("namespace") or namespace
                        if not name:
                            continue
                        try:
                            detail = client.get_http_load_balancer(name=name, namespace=ns)
                        except Exception as e:
                            log.warning(
                                "lb_detail_fetch_failed",
                                name=name, namespace=ns, error=str(e),
                            )
                            continue
                        items.append({
                            **stub,
                            "spec": detail.get("spec") or detail.get("get_spec") or {},
                            "system_metadata": detail.get("system_metadata") or stub.get("system_metadata"),
                        })

                    for item in items:
                        fields = extract_lb_fields(item)
                        stmt = insert(LoadBalancer).values(
                            tenant_id=tenant.id,
                            namespace=fields["namespace"] or namespace,
                            name=fields["name"],
                            domains=fields["domains"],
                            lb_type=fields["lb_type"],
                            advertise_mode=fields["advertise_mode"],
                            advertised_sites=fields["advertised_sites"],
                            has_waf=fields["has_waf"],
                            has_service_policy=fields["has_service_policy"],
                            has_bot_defense=fields["has_bot_defense"],
                            has_api_protection=fields["has_api_protection"],
                            origin_pool_refs=fields["origin_pool_refs"],
                            cert_ref=fields["cert_ref"],
                            raw_spec=fields["raw_spec"],
                            last_seen_at=sync_started_at,
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["tenant_id", "namespace", "name"],
                            set_={
                                "domains": stmt.excluded.domains,
                                "lb_type": stmt.excluded.lb_type,
                                "advertise_mode": stmt.excluded.advertise_mode,
                                "advertised_sites": stmt.excluded.advertised_sites,
                                "has_waf": stmt.excluded.has_waf,
                                "has_service_policy": stmt.excluded.has_service_policy,
                                "has_bot_defense": stmt.excluded.has_bot_defense,
                                "has_api_protection": stmt.excluded.has_api_protection,
                                "origin_pool_refs": stmt.excluded.origin_pool_refs,
                                "cert_ref": stmt.excluded.cert_ref,
                                "raw_spec": stmt.excluded.raw_spec,
                                "last_seen_at": stmt.excluded.last_seen_at,
                            },
                        )
                        db.execute(stmt)
                        tenant_total += 1
                        total += 1

                    successful_namespaces.append(namespace)
                    log.info(
                        "sync_loadbalancers_namespace_done",
                        tenant=tenant.name, namespace=namespace, count=len(items),
                    )

            # v0.8.0 — stale-row reaping. Reap rows in namespaces we
            # SUCCESSFULLY listed (not those that errored out — could wipe
            # legitimate data on a transient failure). Per-namespace scope:
            # last_seen_at < sync_started_at AND namespace IN (succeeded_list).
            reaped = 0
            if successful_namespaces:
                reaped = db.execute(
                    delete(LoadBalancer).where(
                        LoadBalancer.tenant_id == tenant.id,
                        LoadBalancer.namespace.in_(successful_namespaces),
                        LoadBalancer.last_seen_at < sync_started_at,
                    )
                ).rowcount or 0
                if reaped:
                    log.info(
                        "sync_loadbalancers_reaped_stale",
                        tenant=tenant.name,
                        namespaces=successful_namespaces,
                        count=reaped,
                    )

            log.info(
                "sync_loadbalancers_tenant_done",
                tenant=tenant.name,
                namespaces=successful_namespaces,
                count=tenant_total,
                reaped=reaped,
            )
    log.info("sync_loadbalancers_complete", total=total)
    return {"load_balancers": total}
