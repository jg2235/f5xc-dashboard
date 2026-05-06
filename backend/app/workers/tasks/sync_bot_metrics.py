"""Pull bot metric counters per LB → bot_metrics_1min hypertable.

Same pattern as sync_waf_metrics but with bot-specific metric names
(loadbalancer.bot_request_count etc). The 1-hour rollup is maintained
automatically by the TimescaleDB continuous aggregate set up in the
slice 5 migration.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.f5xc.bot_transformers import extract_bot_metric_buckets
from app.f5xc.client import F5XCClient, F5XCError
from app.logging_config import get_logger
from app.models import BotMetric1Min, LoadBalancer
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


# Bot metrics requires a different metric_names list than WAF; we monkey-patch
# the get_metrics body instead of cluttering the client. The client method is
# generic enough — we just need different metric names.
_BOT_METRICS = [
    "loadbalancer.bot_request_count",
    "loadbalancer.bot_challenge_count",
    "loadbalancer.bot_block_count",
    "loadbalancer.bot_allow_count",
]


def _get_bot_metrics(client: F5XCClient, lb_name: str, namespace: str,
                     start_time: str, end_time: str) -> dict:
    """Wrapper around client._request that uses bot metric names."""
    body = {
        "namespace": namespace,
        "lb_name": lb_name,
        "start_time": start_time,
        "end_time": end_time,
        "step": "60s",
        "metric_names": _BOT_METRICS,
    }
    return client._request(  # noqa: SLF001 — internal client call to avoid duplicating retry logic
        "POST",
        f"/api/data/namespaces/{namespace}/metrics/multi_v2",
        json=body,
    )


@celery_app.task(name="app.workers.tasks.sync_bot_metrics.sync_bot_metrics")
def sync_bot_metrics() -> dict:
    settings = get_settings()
    if not settings.analytics_enabled:
        log.info("sync_bot_metrics_skipped_analytics_disabled")
        return {"skipped": True, "reason": "analytics_disabled"}
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(minutes=settings.bot_metrics_window_minutes)

    total_buckets = 0
    total_lbs = 0

    with session_scope() as db:
        tenants = iter_tenants(db)
        if not tenants:
            return {"buckets": 0, "lbs": 0}

        for tenant in tenants:
            # Pull metrics only for LBs with bot defense enabled. Quieter than WAF
            # which queries all LBs (request_count is interesting tenant-wide for WAF).
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
                    try:
                        payload = _get_bot_metrics(
                            client, lb.name, lb.namespace,
                            _iso_z(start), _iso_z(end),
                        )
                    except F5XCError as exc:
                        log.warning(
                            "bot_metrics_api_error",
                            lb=lb.name, status=exc.status_code,
                        )
                        continue

                    buckets = extract_bot_metric_buckets(
                        payload, lb_namespace=lb.namespace, lb_name=lb.name,
                    )
                    for bucket_time, vals in buckets.items():
                        stmt = insert(BotMetric1Min).values(
                            bucket_time=bucket_time,
                            tenant_id=tenant.id,
                            lb_namespace=lb.namespace,
                            lb_name=lb.name,
                            request_count=int(vals.get("request_count", 0)),
                            challenge_count=int(vals.get("challenge_count", 0)),
                            block_count=int(vals.get("block_count", 0)),
                            allow_count=int(vals.get("allow_count", 0)),
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=[
                                "bucket_time", "tenant_id", "lb_namespace", "lb_name",
                            ],
                            set_={
                                "request_count": stmt.excluded.request_count,
                                "challenge_count": stmt.excluded.challenge_count,
                                "block_count": stmt.excluded.block_count,
                                "allow_count": stmt.excluded.allow_count,
                            },
                        )
                        db.execute(stmt)
                        total_buckets += 1

                    total_lbs += 1

    log.info("sync_bot_metrics_complete", buckets=total_buckets, lbs=total_lbs)
    return {"buckets": total_buckets, "lbs": total_lbs}
