"""Evaluate alert rules + cleanup old alerts (slice 7)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.config import get_settings
from app.logging_config import get_logger
from app.models import Alert
from app.security.alerting import evaluate_all_rules
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.evaluate_alert_rules.evaluate_alert_rules")
def evaluate_alert_rules() -> dict:
    settings = get_settings()

    total_counts: dict[str, int] = {}
    tenants_processed = 0

    with session_scope() as db:
        for tenant in iter_tenants(db):
            counts = evaluate_all_rules(db, settings, tenant)
            for k, v in counts.items():
                total_counts[k] = total_counts.get(k, 0) + v
            tenants_processed += 1

    log.info("evaluate_alert_rules_complete", counts=total_counts, tenants=tenants_processed)
    return {"counts": total_counts, "tenants": tenants_processed}


@celery_app.task(name="app.workers.tasks.evaluate_alert_rules.cleanup_old_alerts")
def cleanup_old_alerts() -> dict:
    """Delete resolved alerts older than alert_retention_days."""
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(days=settings.alert_retention_days)
    with session_scope() as db:
        result = db.execute(
            delete(Alert).where(
                Alert.status == "resolved",
                Alert.resolved_at.is_not(None),
                Alert.resolved_at < cutoff,
            )
        )
        deleted = result.rowcount or 0
    log.info("cleanup_old_alerts_complete", deleted=deleted, cutoff_days=settings.alert_retention_days)
    return {"deleted": deleted}
