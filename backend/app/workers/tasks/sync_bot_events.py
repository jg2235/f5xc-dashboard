"""Pull bot events from BOTH sources → bot_events hypertable.

Per cycle, for each tenant:
  1. List LBs with has_bot_defense=True.
  2. For each such LB:
     a. Pull security_events (same endpoint sync_waf_events uses) and filter
        for events with bot_defense fields → BotEvent rows with source="standard".
     b. Pull bot_traffic (BD-A endpoint) → BotEvent rows with source="bd_advanced".
  3. Idempotent: PK is (event_time, id) so re-runs deduplicate.

Cost note: step 2a piggybacks on the same security_events query that
sync_waf_events makes during its own cycle. We re-issue the query here to
keep slice 5 self-contained (no cross-task coupling); F5 XC's response cache
makes the duplicate call cheap. If polling pressure becomes an issue, the
standard ingest could be moved into sync_waf_events.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.f5xc.bot_transformers import (
    extract_bot_event_from_bda,
    extract_bot_event_from_security,
    is_bot_event,
)
from app.f5xc.client import F5XCClient, F5XCError
from app.logging_config import get_logger
from app.models import BotEvent, LoadBalancer
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


@celery_app.task(name="app.workers.tasks.sync_bot_events.sync_bot_events")
def sync_bot_events() -> dict:
    settings = get_settings()
    if not settings.analytics_enabled:
        log.info("sync_bot_events_skipped_analytics_disabled")
        return {"skipped": True, "reason": "analytics_disabled"}
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(minutes=settings.bot_event_window_minutes)

    totals = {"standard": 0, "bd_advanced": 0}
    total_lbs = 0

    with session_scope() as db:
        tenants = iter_tenants(db)
        if not tenants:
            return {"sources": totals, "lbs": 0}

        for tenant in tenants:
            lbs = db.execute(
                select(LoadBalancer).where(
                    LoadBalancer.tenant_id == tenant.id,
                    LoadBalancer.has_bot_defense.is_(True),
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
                    # --- Standard source ---
                    try:
                        sec_payload = client.get_security_events(
                            lb_name=lb.name,
                            namespace=lb.namespace,
                            start_time=_iso_z(start),
                            end_time=_iso_z(end),
                            max_events=settings.bot_max_events_per_cycle,
                        )
                    except F5XCError as exc:
                        log.warning(
                            "bot_events_security_api_error",
                            lb=lb.name, status=exc.status_code,
                        )
                        sec_payload = {"events": []}

                    for raw in sec_payload.get("events") or []:
                        if not is_bot_event(raw):
                            continue
                        fields = extract_bot_event_from_security(
                            raw, lb_namespace=lb.namespace, lb_name=lb.name,
                        )
                        if fields is None:
                            continue
                        stmt = insert(BotEvent).values(
                            id=uuid.uuid4(),
                            tenant_id=tenant.id,
                            **fields,
                        )
                        stmt = stmt.on_conflict_do_nothing(
                            index_elements=["event_time", "id"]
                        )
                        db.execute(stmt)
                        totals["standard"] += 1

                    # --- BD-A source ---
                    try:
                        bda_payload = client.get_bot_traffic(
                            lb_name=lb.name,
                            namespace=lb.namespace,
                            start_time=_iso_z(start),
                            end_time=_iso_z(end),
                            max_events=settings.bot_max_events_per_cycle,
                        )
                    except F5XCError as exc:
                        log.warning(
                            "bot_events_bda_api_error",
                            lb=lb.name, status=exc.status_code,
                        )
                        bda_payload = {"events": []}

                    bda_events = bda_payload.get("events") or []
                    if len(bda_events) >= settings.bot_max_events_per_cycle:
                        log.warning(
                            "bot_events_circuit_breaker_hit",
                            lb=lb.name, source="bd_advanced",
                            count=len(bda_events),
                            limit=settings.bot_max_events_per_cycle,
                        )

                    for raw in bda_events:
                        fields = extract_bot_event_from_bda(
                            raw, lb_namespace=lb.namespace, lb_name=lb.name,
                        )
                        if fields is None:
                            continue
                        stmt = insert(BotEvent).values(
                            id=uuid.uuid4(),
                            tenant_id=tenant.id,
                            **fields,
                        )
                        stmt = stmt.on_conflict_do_nothing(
                            index_elements=["event_time", "id"]
                        )
                        db.execute(stmt)
                        totals["bd_advanced"] += 1

                    total_lbs += 1
                    log.debug(
                        "bot_events_lb_done",
                        lb=lb.name,
                        standard_n=totals["standard"],
                        bda_n=totals["bd_advanced"],
                    )

    log.info("sync_bot_events_complete", sources=totals, lbs=total_lbs)
    return {"sources": totals, "lbs": total_lbs}
