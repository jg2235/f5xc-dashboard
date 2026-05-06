"""JWT revocation list backed by Redis sorted set.

Design:
- Single global key `jwt_revoked` (sorted set)
- Member: jti (per-token unique identifier)
- Score: token's `exp` claim as Unix timestamp (used by GC)
- Fail-closed on Redis unreachable: revocation check raises RedisError,
  caller (dependencies.get_current_user) converts to 401. The dashboard
  depends on Redis for rate limiting + worker queues anyway, so a Redis
  outage already means degraded operation; closing the auth check is
  consistent.

Operational notes:
- Tokens issued before this module shipped lack `jti`. Callers should
  treat missing jti as "skip revocation check" — those tokens expire
  naturally within their TTL.
- GC task (workers/tasks/jwt_gc.py) periodically removes entries whose
  exp has passed, keeping the set small.
"""
from __future__ import annotations

import time

import redis

from app.config import get_settings
from app.logging_config import get_logger

log = get_logger(__name__)

_REVOKED_KEY = "jwt_revoked"
_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    """Lazy-init module-global Redis client. Connection is reused."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
    return _client


def revoke_jti(jti: str, exp_unix: int) -> None:
    """Add a jti to the revocation set with its exp as score.

    Idempotent — re-revoking a jti is a no-op (ZADD returns 0 if member
    exists, 1 if added, but we don't care which).

    Raises redis.RedisError if Redis is unreachable. Callers should
    catch and decide how to surface (login/logout endpoints typically
    log + continue; the cookie clearing already happened).
    """
    client = _get_client()
    client.zadd(_REVOKED_KEY, {jti: exp_unix})


def is_revoked(jti: str) -> bool:
    """Check if a jti is on the revocation list.

    Raises redis.RedisError on connection failure. Caller (auth
    dependency) treats this as fail-closed -> 401.
    """
    client = _get_client()
    score = client.zscore(_REVOKED_KEY, jti)
    return score is not None


def gc_expired(now_unix: int | None = None) -> int:
    """Remove expired entries (score <= now). Returns removal count."""
    client = _get_client()
    if now_unix is None:
        now_unix = int(time.time())
    return client.zremrangebyscore(_REVOKED_KEY, "-inf", now_unix)
