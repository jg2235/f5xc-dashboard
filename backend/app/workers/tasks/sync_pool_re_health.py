"""Sync per-pool per-RE health using the config-plane endpoint status API.

Live mode flow:
  1. GET /api/config/namespaces/{ns}/endpoints — list all endpoint resources
  2. Filter for items named ves-io-origin-pool-* and extract the pool name
     (stripping the ves-io-origin-pool- prefix and trailing UID fragment).
  3. For each matched pool, GET the endpoint detail for per-RE per-origin health.

Mock mode flow:
  Skip the list call; construct endpoint names as ves-io-origin-pool-{pool.name}
  directly, which matches the fixture routing in F5XCClient.

Upserts into the same origin_health table as sync_healthchecks; rows produced
here have site_type resolved from the Sites table (defaults to "re" when the
site is not yet in the DB, since this endpoint only surfaces RE observations).
"""
from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.f5xc.client import F5XCClient, F5XCError
from app.f5xc.transformers import classify_origin_status
from app.logging_config import get_logger
from app.models import OriginHealth, OriginPool, Site, Tenant
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)

# Matches the trailing UID fragment F5 XC appends to endpoint resource names,
# e.g. "-66f6b7b57d" (8–16 lowercase hex chars after the final hyphen).
_UID_SUFFIX_RE = re.compile(r"-[0-9a-f]{8,16}$")


def _build_endpoint_name_map(items: list[dict[str, Any]]) -> dict[str, str]:
    """Map pool_name → full endpoint resource name from a /endpoints list response."""
    out: dict[str, str] = {}
    prefix = "ves-io-origin-pool-"
    for item in items:
        name: str = item.get("name") or ""
        if not name.startswith(prefix):
            continue
        suffix = name[len(prefix):]
        # Strip the UID fragment (last -xxxxxxxx...) to recover the pool name
        pool_name = _UID_SUFFIX_RE.sub("", suffix)
        out[pool_name] = name
    return out


def _extract_ip(discovered_ip: dict[str, Any]) -> str:
    """Pull the first available IP from a discovered_ip structure."""
    ipv4 = (discovered_ip.get("ipv4") or {}).get("addr", "")
    ipv6 = (discovered_ip.get("ipv6") or {}).get("addr", "")
    return ipv4 or ipv6 or ""


def _parse_pool_endpoint_status(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the real F5 XC endpoint status response into per-(RE, origin) dicts.

    Actual response shape (abbreviated):
      {
        "status": [
          {
            "metadata": {"creator_id": "fr4-fra", ...},
            "ver_status": [
              {
                "site": "fr4-fra",
                "discovered_ip": {"ipv4": {"addr": "1.2.3.4"}},
                "discovered_port": 443,
                "health_status": {"<origin-uuid>": "UNHEALTHY"},
                "health_check_details": [
                  {
                    "health_status": "UNHEALTHY",
                    "health_status_update_time": "<iso>",
                    "health_status_failure_reason": "http_stream_reset"
                  }
                ]
              }
            ]
          }
        ]
      }
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int | None]] = set()  # deduplicate (site, addr, port)

    for status_entry in response.get("status", []):
        meta = status_entry.get("metadata") or {}
        site_name = meta.get("creator_id", "")
        if not site_name:
            continue

        for ver in status_entry.get("ver_status", []):
            address = _extract_ip(ver.get("discovered_ip") or {})
            port = ver.get("discovered_port")
            key = (site_name, address, port)
            if key in seen:
                continue  # already captured a row for this (RE, origin)
            seen.add(key)

            # Most reliable health comes from health_check_details
            hc_details = ver.get("health_check_details") or []
            if hc_details:
                hc = hc_details[0]
                health_status = (hc.get("health_status") or "UNKNOWN").upper()
                last_probe = hc.get("health_status_update_time")
                failure_reason = hc.get("health_status_failure_reason") or None
                if failure_reason == "":
                    failure_reason = None
            else:
                # Fall back to the aggregate health_status dict
                hs_dict = ver.get("health_status") or {}
                health_status = (next(iter(hs_dict.values()), "UNKNOWN") or "UNKNOWN").upper()
                last_probe = None
                failure_reason = None

            if not address:
                continue

            out.append(
                {
                    "site_name": site_name,
                    "address": address,
                    "port": port,
                    "status": health_status,
                    "consecutive_failures": 0,
                    "last_probe": last_probe,
                    "failure_reason": failure_reason,
                }
            )
    return out


def _maybe_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    s2 = s[:-1] + "+00:00" if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(s2)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _upsert_re_health(
    db: Session,
    *,
    tenant_id: Any,
    pool: OriginPool,
    entry: dict[str, Any],
    site_type: str,
    now: datetime,
) -> None:
    raw_status = entry["status"]
    classified = classify_origin_status(raw_status)
    stmt = insert(OriginHealth).values(
        tenant_id=tenant_id,
        pool_id=pool.id,
        origin_address=entry["address"],
        origin_port=entry.get("port"),
        site_name=entry["site_name"],
        site_type=site_type,
        raw_status=raw_status,
        classified_status=classified,
        consecutive_failures=entry["consecutive_failures"],
        failure_reason=entry.get("failure_reason"),
        last_status_change=None,
        last_probe_at=_maybe_iso(entry.get("last_probe")),
        last_seen_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["pool_id", "origin_address", "origin_port", "site_name"],
        set_={
            "site_type": stmt.excluded.site_type,
            "raw_status": stmt.excluded.raw_status,
            "classified_status": stmt.excluded.classified_status,
            "consecutive_failures": stmt.excluded.consecutive_failures,
            "failure_reason": stmt.excluded.failure_reason,
            "last_probe_at": stmt.excluded.last_probe_at,
            "last_seen_at": stmt.excluded.last_seen_at,
        },
    )
    db.execute(stmt)


def _rollup_pool(db: Session, pool: OriginPool, now: datetime) -> None:
    rows = db.execute(
        select(OriginHealth.classified_status).where(OriginHealth.pool_id == pool.id)
    ).scalars().all()
    pool.healthy_count = sum(1 for s in rows if s == "healthy")
    pool.unhealthy_count = sum(1 for s in rows if s == "unhealthy")
    pool.warning_count = sum(1 for s in rows if s == "warning")
    pool.last_healthcheck_at = now


@celery_app.task(name="app.workers.tasks.sync_pool_re_health.sync_pool_re_health")
def sync_pool_re_health() -> dict:
    settings = get_settings()
    delay = settings.healthcheck_per_request_delay_ms / 1000.0

    rows_upserted = 0
    pools_done = 0
    pools_skipped = 0
    errors = 0

    with session_scope() as db:
        tenants: list[Tenant] = iter_tenants(db)
        if not tenants:
            return {"tenants": 0, "rows": 0}

        for tenant in tenants:
            sites_by_name = {
                s.name: s
                for s in db.execute(
                    select(Site).where(Site.tenant_id == tenant.id)
                ).scalars().all()
            }
            pools = list(
                db.execute(
                    select(OriginPool).where(OriginPool.tenant_id == tenant.id)
                ).scalars().all()
            )
            if not pools:
                continue

            with F5XCClient(
                tenant=tenant.f5xc_tenant,
                api_token=settings.f5xc_api_token or tenant.f5xc_api_token,
                namespace=tenant.f5xc_namespace,
                mock=settings.f5xc_mock,
                timeout=settings.f5xc_request_timeout_seconds,
                max_retries=settings.f5xc_max_retries,
                api_url_template=settings.f5xc_api_url_template,
            ) as client:
                now = datetime.now(UTC)

                if settings.f5xc_mock:
                    # Mock: construct names directly (matches pool_endpoint__{name}.json fixtures)
                    endpoint_name_map = {
                        p.name: f"ves-io-origin-pool-{p.name}" for p in pools
                    }
                else:
                    # Live: list all endpoint resources per namespace to get full names with UID
                    endpoint_name_map: dict[str, str] = {}
                    for ns in tenant.effective_namespaces:
                        try:
                            items = client.list_pool_endpoint_resources(namespace=ns)
                            endpoint_name_map.update(_build_endpoint_name_map(items))
                        except F5XCError as exc:
                            log.warning(
                                "sync_pool_re_health_list_error",
                                namespace=ns,
                                status=exc.status_code,
                            )

                for pool in pools:
                    endpoint_name = endpoint_name_map.get(pool.name)
                    if not endpoint_name:
                        log.debug("sync_pool_re_health_no_endpoint", pool=pool.name)
                        pools_skipped += 1
                        continue

                    try:
                        response = client.get_pool_endpoint_status(
                            endpoint_name, namespace=pool.namespace
                        )
                    except F5XCError as exc:
                        errors += 1
                        log.warning(
                            "sync_pool_re_health_api_error",
                            pool=pool.name,
                            endpoint=endpoint_name,
                            status=exc.status_code,
                        )
                        if delay:
                            time.sleep(delay)
                        continue

                    entries = _parse_pool_endpoint_status(response)
                    for entry in entries:
                        site_obj = sites_by_name.get(entry["site_name"])
                        # This endpoint ONLY surfaces RE observations, so override
                        # unknown site_types with "re" rather than carrying forward
                        # an ambiguous classification from the Sites table.
                        site_type = site_obj.site_type if (site_obj and site_obj.site_type not in (None, "unknown")) else "re"
                        _upsert_re_health(
                            db,
                            tenant_id=tenant.id,
                            pool=pool,
                            entry=entry,
                            site_type=site_type,
                            now=now,
                        )
                        rows_upserted += 1

                    _rollup_pool(db, pool, now)
                    pools_done += 1

                    if delay:
                        time.sleep(delay)

    log.info(
        "sync_pool_re_health_complete",
        pools=pools_done,
        pools_skipped=pools_skipped,
        rows=rows_upserted,
        errors=errors,
    )
    return {
        "pools": pools_done,
        "pools_skipped": pools_skipped,
        "rows": rows_upserted,
        "errors": errors,
    }
