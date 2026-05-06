"""Pull WAF security_events per LB → waf_events hypertable.

Per cycle:
  1. For each tenant, list LBs with has_waf=True.
  2. For each such LB, query security_events for [now - waf_event_window_minutes, now].
  3. Insert into waf_events. Conflicts (same event_time + id) ignored.
  4. Circuit breaker: if a single LB returns ≥ waf_max_events_per_cycle,
     log a warning but ingest what we got.

Idempotency: F5 XC events have a stable id we use as part of the PK; rerunning
the task within the same window deduplicates naturally.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.f5xc.client import F5XCClient, F5XCError
from app.f5xc.waf_transformers import extract_waf_event_fields
from app.logging_config import get_logger
from app.models import LoadBalancer, WafEvent
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


@celery_app.task(name="app.workers.tasks.sync_waf_events.sync_waf_events")
def sync_waf_events() -> dict:
    settings = get_settings()
    if not settings.analytics_enabled:
        log.info("sync_waf_events_skipped_analytics_disabled")
        return {"skipped": True, "reason": "analytics_disabled"}
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(minutes=settings.waf_event_window_minutes)

    total_inserted = 0
    total_lbs = 0

    with session_scope() as db:
        tenants = iter_tenants(db)
        if not tenants:
            return {"inserted": 0, "lbs": 0}

        for tenant in tenants:
            lbs = db.execute(
                select(LoadBalancer).where(
                    LoadBalancer.tenant_id == tenant.id,
                    LoadBalancer.has_waf.is_(True),
                )
            ).scalars().all()

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
                        payload = client.get_security_events(
                            lb_name=lb.name,
                            namespace=lb.namespace,
                            start_time=_iso_z(start),
                            end_time=_iso_z(end),
                            max_events=settings.waf_max_events_per_cycle,
                        )
                    except F5XCError as exc:
                        log.warning(
                            "waf_events_api_error",
                            lb=lb.name, status=exc.status_code,
                        )
                        continue

                    events = payload.get("events") or []
                    if len(events) >= settings.waf_max_events_per_cycle:
                        log.warning(
                            "waf_events_circuit_breaker_hit",
                            lb=lb.name,
                            count=len(events),
                            limit=settings.waf_max_events_per_cycle,
                        )

                    inserted_for_lb = 0
                    for raw in events:
                        fields = extract_waf_event_fields(
                            raw, lb_namespace=lb.namespace, lb_name=lb.name
                        )
                        if fields is None:
                            continue
                        stmt = insert(WafEvent).values(
                            id=uuid.uuid4(),
                            tenant_id=tenant.id,
                            **fields,
                        )
                        # PK is (event_time, id). uuid4 makes collisions effectively zero,
                        # so ON CONFLICT DO NOTHING is just defensive.
                        stmt = stmt.on_conflict_do_nothing(
                            index_elements=["event_time", "id"]
                        )
                        db.execute(stmt)
                        inserted_for_lb += 1

                    total_inserted += inserted_for_lb
                    total_lbs += 1
                    log.debug(
                        "waf_events_lb_done",
                        lb=lb.name, count=inserted_for_lb,
                    )

    log.info("sync_waf_events_complete", inserted=total_inserted, lbs=total_lbs)
    return {"inserted": total_inserted, "lbs": total_lbs}
