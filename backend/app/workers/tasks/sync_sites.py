"""Sync F5 XC sites (RE/CE/virtual) → DB. Used by sync_healthchecks to expand
the ALL_RE_SITES_SENTINEL into concrete site names.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.f5xc.client import F5XCClient
from app.f5xc.transformers import extract_site_fields
from app.logging_config import get_logger
from app.models import Site
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.sync_sites.sync_sites")
def sync_sites() -> dict:
    settings = get_settings()
    total = 0
    detail_ok = 0
    detail_404 = 0
    with session_scope() as db:
        tenants = iter_tenants(db)
        if not tenants:
            return {"tenants": 0, "sites": 0}

        for tenant in tenants:
            with F5XCClient(
                tenant=tenant.f5xc_tenant,
                api_token=settings.f5xc_api_token or tenant.f5xc_api_token,
                namespace=tenant.f5xc_namespace,
                mock=settings.f5xc_mock,
                timeout=settings.f5xc_request_timeout_seconds,
                max_retries=settings.f5xc_max_retries,
                api_url_template=settings.f5xc_api_url_template,
            ) as client:
                listed = client.list_sites()

                # Per-site detail GET hydrates the spec needed for site_type
                # classification. F5 XC restricts detail on the system
                # namespace for many tokens — typically RE sites 404 while CE
                # sites return 200. Sites that 404 fall back to the name
                # heuristic in extract_site_fields().
                items = []
                for stub in listed:
                    name = stub.get("name", "")
                    if not name:
                        continue
                    detail = None
                    try:
                        detail = client.get_site(name)
                    except Exception as e:
                        # Don't crash the whole task on per-site error
                        log.warning(
                            "site_detail_fetch_failed",
                            name=name, error=str(e),
                        )
                    if detail is not None:
                        detail_ok += 1
                        items.append({
                            **stub,
                            "spec": detail.get("spec") or detail.get("get_spec") or {},
                            "system_metadata": detail.get("system_metadata") or stub.get("system_metadata"),
                        })
                    else:
                        detail_404 += 1
                        # Pass through the stub — extract_site_fields will
                        # use the name heuristic.
                        items.append(stub)

            sync_started_at = datetime.now(UTC)
            for item in items:
                fields = extract_site_fields(item)
                if not fields["name"]:
                    continue
                stmt = insert(Site).values(
                    tenant_id=tenant.id,
                    name=fields["name"],
                    site_type=fields["site_type"],
                    operational_status=fields["operational_status"],
                    region=fields["region"],
                    provider=fields["provider"],
                    raw_spec=fields["raw_spec"],
                    last_seen_at=sync_started_at,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["tenant_id", "name"],
                    set_={
                        "site_type": stmt.excluded.site_type,
                        "operational_status": stmt.excluded.operational_status,
                        "region": stmt.excluded.region,
                        "provider": stmt.excluded.provider,
                        "raw_spec": stmt.excluded.raw_spec,
                        "last_seen_at": stmt.excluded.last_seen_at,
                    },
                )
                db.execute(stmt)
                total += 1

            # v0.8.0 — stale-row reaping. Sites are tenant-global (no namespace
            # in the unique index), so the reap predicate scopes by tenant only.
            reaped = 0
            if items:
                reaped = db.execute(
                    delete(Site).where(
                        Site.tenant_id == tenant.id,
                        Site.last_seen_at < sync_started_at,
                    )
                ).rowcount or 0
                if reaped:
                    log.info(
                        "sync_sites_reaped_stale",
                        tenant=tenant.name,
                        count=reaped,
                    )

            log.info(
                "sync_sites_tenant_done",
                tenant=tenant.name,
                count=len(items),
                detail_hydrated=detail_ok,
                detail_404=detail_404,
                reaped=reaped,
            )
    return {"sites": total, "detail_hydrated": detail_ok, "detail_404": detail_404}
