"""Daily cleanup of expired audit events.

Retention is governed by `Settings.audit_retention_days` (default 180).
Schedule via celery beat — see `app.celery_app` for the schedule entry.

The task is idempotent and safe to run on an empty table.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.config import get_settings
from app.db import SessionLocal  # type: ignore[attr-defined]
from app.logging_config import get_logger
from app.models import AuditEvent

# Import path follows the project convention seen elsewhere in the repo.
# If your celery app instance lives at a different path, adjust the import.
from app.workers.celery_app import celery_app  # type: ignore[attr-defined]

log = get_logger(__name__)


@celery_app.task(name="audit.cleanup_audit_events")
def cleanup_audit_events() -> dict:
    """Delete audit_events older than AUDIT_RETENTION_DAYS.

    Returns a small dict for observability (cutoff timestamp + rowcount).
    """
    settings = get_settings()
    days = max(int(settings.audit_retention_days), 1)
    cutoff = datetime.now(UTC) - timedelta(days=days)

    with SessionLocal() as db:
        result = db.execute(
            delete(AuditEvent).where(AuditEvent.created_at < cutoff)
        )
        db.commit()
        deleted = result.rowcount or 0

    log.info(
        "audit_cleanup_complete",
        retention_days=days,
        cutoff=cutoff.isoformat(),
        deleted=deleted,
    )
    return {"cutoff": cutoff.isoformat(), "deleted": deleted}
