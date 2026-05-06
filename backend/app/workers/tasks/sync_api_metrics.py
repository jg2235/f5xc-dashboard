"""Sync per-endpoint metrics → api_metrics_1min hypertable.

Pulls metrics_multi_v2 grouped by (method, endpoint) for each LB. Each
LB produces one bucket per minute per (method, endpoint) tuple.

Cost note: this can be the heaviest sync task in the system. An LB with
500 endpoints × 10 buckets per cycle = 5000 rows per cycle. The 1-hour
continuous aggregate compresses this for medium-term queries.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.f5xc.api_transformers import extract_api_endpoint_metric_buckets
from app.f5xc.client import F5XCClient, F5XCError
from app.logging_config import get_logger
from app.models import ApiMetric1Min, LoadBalancer
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


@celery_app.task(name="app.workers.tasks.sync_api_metrics.sync_api_metrics")
def sync_api_metrics() -> dict:
    settings = get_settings()
    if not settings.analytics_enabled:
        log.info("sync_api_metrics_skipped_analytics_disabled")
        return {"skipped": True, "reason": "analytics_disabled"}
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(minutes=settings.api_metrics_window_minutes)

    total_buckets = 0
    total_lbs = 0

    with session_scope() as db:
        tenants = iter_tenants(db)
        if not tenants:
            return {"buckets": 0, "lbs": 0}

        for tenant in tenants:
            lbs = db.execute(
                select(LoadBalancer).where(LoadBalancer.tenant_id == tenant.id)
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
                        payload = client.get_api_endpoint_metrics(
                            lb_name=lb.name,
                            namespace=lb.namespace,
                            start_time=_iso_z(start),
                            end_time=_iso_z(end),
                        )
                    except F5XCError as exc:
                        log.warning(
                            "api_metrics_api_error",
                            lb=lb.name, status=exc.status_code,
                        )
                        continue

                    buckets = extract_api_endpoint_metric_buckets(
                        payload, lb_namespace=lb.namespace, lb_name=lb.name,
                    )
                    for (bucket_time, method, endpoint), vals in buckets.items():
                        stmt = insert(ApiMetric1Min).values(
                            bucket_time=bucket_time,
                            tenant_id=tenant.id,
                            lb_namespace=lb.namespace,
                            lb_name=lb.name,
                            method=method,
                            endpoint_path=endpoint,
                            request_count=int(vals.get("request_count", 0)),
                            error_4xx_count=int(vals.get("error_4xx_count", 0)),
                            error_5xx_count=int(vals.get("error_5xx_count", 0)),
                            latency_p50_ms=vals.get("latency_p50_ms"),
                            latency_p95_ms=vals.get("latency_p95_ms"),
                            latency_p99_ms=vals.get("latency_p99_ms"),
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=[
                                "bucket_time", "tenant_id", "lb_namespace", "lb_name",
                                "method", "endpoint_path",
                            ],
                            set_={
                                "request_count": stmt.excluded.request_count,
                                "error_4xx_count": stmt.excluded.error_4xx_count,
                                "error_5xx_count": stmt.excluded.error_5xx_count,
                                "latency_p50_ms": stmt.excluded.latency_p50_ms,
                                "latency_p95_ms": stmt.excluded.latency_p95_ms,
                                "latency_p99_ms": stmt.excluded.latency_p99_ms,
                            },
                        )
                        db.execute(stmt)
                        total_buckets += 1

                    total_lbs += 1

    log.info("sync_api_metrics_complete", buckets=total_buckets, lbs=total_lbs)
    return {"buckets": total_buckets, "lbs": total_lbs}
