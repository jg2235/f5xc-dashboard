"""Garbage-collect expired entries from the JWT revocation list.

Each revoked jti has its `exp` claim as the score in the redis sorted set.
Once exp is in the past, the entry serves no purpose — the token can't be
verified anymore (jwt.decode raises on expired tokens before reaching the
revocation check). Removing it keeps the set small.

Runs daily at low frequency. Single ZREMRANGEBYSCORE call: O(log N + M)
where M is the count of expired entries.
"""
from __future__ import annotations

import time

from app.auth.revocation import gc_expired
from app.logging_config import get_logger
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.jwt_gc.gc_revoked_jtis")
def gc_revoked_jtis() -> dict:
    now_unix = int(time.time())
    try:
        removed = gc_expired(now_unix=now_unix)
    except Exception as e:  # noqa: BLE001
        log.warning("jwt_revocation_gc_failed", error=str(e))
        return {"ok": False, "error": str(e)}
    log.info("jwt_revocation_gc_complete", removed=removed)
    return {"ok": True, "removed": removed}
