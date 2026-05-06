"""Pull WAF metrics per LB → waf_metrics_1min hypertable.

Per cycle:
  1. For each tenant, list ALL LBs (we want request_count even on non-WAF LBs).
  2. For each LB, query metrics for [now - waf_metrics_window_minutes, now] at 60s step.
  3. Upsert per (bucket_time, tenant_id, lb_namespace, lb_name).

The 1-hour rollups are maintained automatically by the TimescaleDB
continuous aggregate set up in the slice 4 migration.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.f5xc.client import F5XCClient, F5XCError
from app.f5xc.waf_transformers import extract_metric_buckets
from app.logging_config import get_logger
from app.models import LoadBalancer, WafMetric1Min
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


@celery_app.task(name="app.workers.tasks.sync_waf_metrics.sync_waf_metrics")
def sync_waf_metrics() -> dict:
    settings = get_settings()
    if not settings.analytics_enabled:
        log.info("sync_waf_metrics_skipped_analytics_disabled")
        return {"skipped": True, "reason": "analytics_disabled"}
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(minutes=settings.waf_metrics_window_minutes)

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
                        payload = client.get_metrics(
                            lb_name=lb.name,
                            namespace=lb.namespace,
                            start_time=_iso_z(start),
                            end_time=_iso_z(end),
                            step="60s",
                        )
                    except F5XCError as exc:
                        log.warning(
                            "waf_metrics_api_error",
                            lb=lb.name, status=exc.status_code,
                        )
                        continue

                    buckets = extract_metric_buckets(
                        payload, lb_namespace=lb.namespace, lb_name=lb.name
                    )
                    for bucket_time, vals in buckets.items():
                        stmt = insert(WafMetric1Min).values(
                            bucket_time=bucket_time,
                            tenant_id=tenant.id,
                            lb_namespace=lb.namespace,
                            lb_name=lb.name,
                            request_count=int(vals.get("request_count", 0)),
                            blocked_count=int(vals.get("blocked_count", 0)),
                            monitored_count=int(vals.get("monitored_count", 0)),
                            error_count=int(vals.get("error_count", 0)),
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=[
                                "bucket_time", "tenant_id", "lb_namespace", "lb_name"
                            ],
                            set_={
                                "request_count": stmt.excluded.request_count,
                                "blocked_count": stmt.excluded.blocked_count,
                                "monitored_count": stmt.excluded.monitored_count,
                                "error_count": stmt.excluded.error_count,
                            },
                        )
                        db.execute(stmt)
                        total_buckets += 1

                    total_lbs += 1

    log.info("sync_waf_metrics_complete", buckets=total_buckets, lbs=total_lbs)
    return {"buckets": total_buckets, "lbs": total_lbs}
