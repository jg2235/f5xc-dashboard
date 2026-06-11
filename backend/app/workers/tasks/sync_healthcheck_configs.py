"""Sync health check config objects from F5 XC → DB.

Origin pools reference standalone healthcheck objects (spec.healthcheck[]).
This task lists + hydrates those objects per namespace so the dashboard can
show how each pool's health check is configured (protocol, path, thresholds,
interval/timeout, expected status codes), not just its name.

Distinct from `sync_healthchecks`, which fetches per-origin per-site probe
*results* — this fetches the health check *configuration* objects.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.f5xc.client import F5XCClient
from app.f5xc.transformers import extract_healthcheck_fields
from app.logging_config import get_logger
from app.models import HealthCheck
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.sync_healthcheck_configs.sync_healthcheck_configs")
def sync_healthcheck_configs() -> dict:
    settings = get_settings()
    total = 0
    with session_scope() as db:
        tenants = iter_tenants(db)
        if not tenants:
            return {"tenants": 0, "health_checks": 0}

        for tenant in tenants:
            namespaces = tenant.effective_namespaces
            sync_started_at = datetime.now(UTC)
            successful_namespaces: list[str] = []
            tenant_total = 0

            with F5XCClient(
                tenant=tenant.f5xc_tenant,
                api_token=settings.f5xc_api_token or tenant.f5xc_api_token,
                namespace=tenant.f5xc_namespace,
                mock=settings.f5xc_mock,
                timeout=settings.f5xc_request_timeout_seconds,
                max_retries=settings.f5xc_max_retries,
                api_url_template=settings.f5xc_api_url_template,
            ) as client:
                for namespace in namespaces:
                    try:
                        listed = client.list_healthchecks(namespace=namespace)
                    except Exception as exc:
                        log.warning(
                            "sync_healthcheck_configs_list_failed",
                            tenant=tenant.name, namespace=namespace, error=str(exc),
                        )
                        continue

                    items = []
                    for stub in listed:
                        name = stub.get("name", "")
                        ns = stub.get("namespace") or namespace
                        if not name:
                            continue
                        try:
                            detail = client.get_healthcheck(name=name, namespace=ns)
                        except Exception as e:
                            log.warning(
                                "healthcheck_detail_fetch_failed",
                                name=name, namespace=ns, error=str(e),
                            )
                            continue
                        items.append({
                            **stub,
                            "spec": detail.get("spec") or detail.get("get_spec") or {},
                        })

                    for item in items:
                        fields = extract_healthcheck_fields(item)
                        if not fields["name"]:
                            continue
                        stmt = insert(HealthCheck).values(
                            tenant_id=tenant.id,
                            namespace=fields["namespace"] or namespace,
                            name=fields["name"],
                            protocol=fields["protocol"],
                            interval_seconds=fields["interval_seconds"],
                            timeout_seconds=fields["timeout_seconds"],
                            healthy_threshold=fields["healthy_threshold"],
                            unhealthy_threshold=fields["unhealthy_threshold"],
                            jitter_percent=fields["jitter_percent"],
                            http_path=fields["http_path"],
                            http_host_header=fields["http_host_header"],
                            http_use_http2=fields["http_use_http2"],
                            expected_status_codes=fields["expected_status_codes"],
                            raw_spec=fields["raw_spec"],
                            last_seen_at=sync_started_at,
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["tenant_id", "namespace", "name"],
                            set_={
                                "protocol": stmt.excluded.protocol,
                                "interval_seconds": stmt.excluded.interval_seconds,
                                "timeout_seconds": stmt.excluded.timeout_seconds,
                                "healthy_threshold": stmt.excluded.healthy_threshold,
                                "unhealthy_threshold": stmt.excluded.unhealthy_threshold,
                                "jitter_percent": stmt.excluded.jitter_percent,
                                "http_path": stmt.excluded.http_path,
                                "http_host_header": stmt.excluded.http_host_header,
                                "http_use_http2": stmt.excluded.http_use_http2,
                                "expected_status_codes": stmt.excluded.expected_status_codes,
                                "raw_spec": stmt.excluded.raw_spec,
                                "last_seen_at": stmt.excluded.last_seen_at,
                            },
                        )
                        db.execute(stmt)
                        tenant_total += 1
                        total += 1

                    successful_namespaces.append(namespace)
                    log.info(
                        "sync_healthcheck_configs_namespace_done",
                        tenant=tenant.name, namespace=namespace, count=len(items),
                    )

            reaped = 0
            if successful_namespaces:
                reaped = db.execute(
                    delete(HealthCheck).where(
                        HealthCheck.tenant_id == tenant.id,
                        HealthCheck.namespace.in_(successful_namespaces),
                        HealthCheck.last_seen_at < sync_started_at,
                    )
                ).rowcount or 0

            log.info(
                "sync_healthcheck_configs_tenant_done",
                tenant=tenant.name,
                namespaces=successful_namespaces,
                count=tenant_total,
                reaped=reaped,
            )
    return {"health_checks": total}
