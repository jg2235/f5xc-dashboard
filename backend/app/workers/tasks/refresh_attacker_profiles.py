"""Refresh attacker profiles cache (slice 7).

Runs every analytics interval. Reads waf_events + bot_events for the
profile window, computes per-attacker aggregates, upserts attacker_profiles.
"""
from __future__ import annotations

from datetime import timedelta

from app.config import get_settings
from app.logging_config import get_logger
from app.security.correlator import correlate_attackers, upsert_attacker_profiles
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.refresh_attacker_profiles.refresh_attacker_profiles"
)
def refresh_attacker_profiles() -> dict:
    settings = get_settings()
    window = timedelta(minutes=settings.security_profile_window_minutes)

    total_attackers = 0
    tenants_processed = 0

    with session_scope() as db:
        for tenant in iter_tenants(db):
            aggregates = correlate_attackers(
                db,
                tenant_id=tenant.id,
                window=window,
                max_attackers=settings.security_max_attackers_per_cycle,
            )
            n = upsert_attacker_profiles(
                db, tenant_id=tenant.id, aggregates=aggregates,
            )
            total_attackers += n
            tenants_processed += 1
            log.debug(
                "attacker_profiles_tenant_done",
                tenant=tenant.f5xc_tenant, attackers=n,
            )

    log.info(
        "refresh_attacker_profiles_complete",
        attackers=total_attackers, tenants=tenants_processed,
    )
    return {"attackers": total_attackers, "tenants": tenants_processed}
