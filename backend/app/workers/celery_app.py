"""Celery app factory and beat schedule."""
from __future__ import annotations

from celery import Celery
from celery.schedules import schedule

from app.config import get_settings
from app.logging_config import configure_logging

configure_logging()
settings = get_settings()

celery_app = Celery(
    "f5xc_dashboard",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.tasks.sync_loadbalancers",
        "app.workers.tasks.sync_certificates",
        "app.workers.tasks.sync_origin_pools",
        "app.workers.tasks.sync_sites",
        "app.workers.tasks.sync_policies",
        "app.workers.tasks.sync_healthchecks",
        "app.workers.tasks.sync_waf_events",
        "app.workers.tasks.sync_waf_metrics",
        "app.workers.tasks.sync_bot_events",
        "app.workers.tasks.sync_bot_metrics",
        "app.workers.tasks.sync_api_endpoints",
        "app.workers.tasks.sync_api_discovery_state",
        "app.workers.tasks.sync_api_metrics",
        "app.workers.tasks.refresh_attacker_profiles",
        "app.workers.tasks.evaluate_alert_rules",
        # v0.7.2 — was scheduled in beat_schedule but never imported here,
        # so the worker silently never executed it. Audit-table GC was a
        # no-op until this fix. Fixed alongside v0.8.0 item 7.
        "app.workers.tasks.audit_cleanup",
        # v0.8.0 item 7 — JWT revocation list GC.
        "app.workers.tasks.jwt_gc",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="f5xc",
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "sync-loadbalancers": {
        "task": "app.workers.tasks.sync_loadbalancers.sync_loadbalancers",
        "schedule": schedule(run_every=settings.poll_config_interval),
    },
    "sync-certificates": {
        "task": "app.workers.tasks.sync_certificates.sync_certificates",
        "schedule": schedule(run_every=settings.poll_config_interval),
    },
    "sync-origin-pools": {
        "task": "app.workers.tasks.sync_origin_pools.sync_origin_pools",
        "schedule": schedule(run_every=settings.poll_config_interval),
    },
    "sync-sites": {
        "task": "app.workers.tasks.sync_sites.sync_sites",
        "schedule": schedule(run_every=settings.poll_config_interval),
    },
    "sync-policies": {
        "task": "app.workers.tasks.sync_policies.sync_policies",
        "schedule": schedule(run_every=settings.poll_config_interval),
    },
    "sync-healthchecks": {
        "task": "app.workers.tasks.sync_healthchecks.sync_healthchecks",
        "schedule": schedule(run_every=settings.poll_healthcheck_interval),
    },
    "sync-waf-events": {
        "task": "app.workers.tasks.sync_waf_events.sync_waf_events",
        "schedule": schedule(run_every=settings.poll_analytics_interval),
    },
    "sync-waf-metrics": {
        "task": "app.workers.tasks.sync_waf_metrics.sync_waf_metrics",
        "schedule": schedule(run_every=settings.poll_analytics_interval),
    },
    "sync-bot-events": {
        "task": "app.workers.tasks.sync_bot_events.sync_bot_events",
        "schedule": schedule(run_every=settings.poll_analytics_interval),
    },
    "sync-bot-metrics": {
        "task": "app.workers.tasks.sync_bot_metrics.sync_bot_metrics",
        "schedule": schedule(run_every=settings.poll_analytics_interval),
    },
    "sync-api-endpoints": {
        "task": "app.workers.tasks.sync_api_endpoints.sync_api_endpoints",
        "schedule": schedule(run_every=settings.poll_config_interval),
    },
    "sync-api-discovery-state": {
        "task": "app.workers.tasks.sync_api_discovery_state.sync_api_discovery_state",
        "schedule": schedule(run_every=settings.poll_config_interval),
    },
    "sync-api-metrics": {
        "task": "app.workers.tasks.sync_api_metrics.sync_api_metrics",
        "schedule": schedule(run_every=settings.poll_analytics_interval),
    },
    # Slice 7 — security analytics + alerting
    "refresh-attacker-profiles": {
        "task": "app.workers.tasks.refresh_attacker_profiles.refresh_attacker_profiles",
        "schedule": schedule(run_every=settings.poll_analytics_interval),
    },
    "evaluate-alert-rules": {
        "task": "app.workers.tasks.evaluate_alert_rules.evaluate_alert_rules",
        "schedule": schedule(run_every=settings.poll_analytics_interval),
    },
    "cleanup-old-alerts": {
        "task": "app.workers.tasks.evaluate_alert_rules.cleanup_old_alerts",
        # Run cleanup once daily — pin to 1h for simplicity here
        "schedule": schedule(run_every=3600),
    },
    # Slice 7.2 — audit log retention (v0.7.2)
    "cleanup-audit-events": {
        "task": "audit.cleanup_audit_events",
        "schedule": schedule(run_every=86400),  # daily
    },
    # v0.8.0 — JWT revocation list GC. Removes entries from the redis
    # sorted set whose token exp has already passed. Daily frequency is
    # appropriate: the set is naturally bounded by max(refresh_ttl) which
    # is 7 days, and growth rate scales with logout/rotation events
    # (low, even at scale).
    "jwt-revocation-gc": {
        "task": "app.workers.tasks.jwt_gc.gc_revoked_jtis",
        "schedule": schedule(run_every=86400),  # daily
    },
}
