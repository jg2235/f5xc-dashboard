"""WAF analytics transformers (slice 4).

Live in their own module to keep transformers.py from growing further.
F5 XC's security_events shape is documented imprecisely — these defaults
match what the live API has emitted in v0.4 testing, with graceful
fallbacks for missing fields.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def extract_waf_event_fields(
    item: dict[str, Any], *, lb_namespace: str, lb_name: str,
) -> dict[str, Any] | None:
    """Flatten a security_events record into WafEvent column shape.

    Returns None if event_time can't be parsed (event is unusable for a hypertable).
    """
    event_time = _parse_iso(item.get("event_time") or item.get("timestamp"))
    if event_time is None:
        return None

    action_raw = (item.get("action") or "").upper()
    # Normalize: F5 sometimes uses "BLOCKED" / "ALLOWED" / "MONITORED"
    action = {
        "BLOCKED": "BLOCK", "BLOCK": "BLOCK",
        "ALLOWED": "ALLOW", "ALLOW": "ALLOW",
        "MONITORED": "MONITOR", "MONITOR": "MONITOR",
    }.get(action_raw, action_raw or "ALLOW")

    waf_policy = item.get("waf_policy") or {}
    return {
        "event_time": event_time,
        "lb_namespace": lb_namespace,
        "lb_name": lb_name,
        "action": action,
        "source_ip": item.get("src_ip") or item.get("source_ip"),
        "source_country": item.get("src_country") or item.get("source_country"),
        "source_asn": item.get("src_asn") or item.get("source_asn"),
        "method": item.get("method"),
        "url": (item.get("url") or "")[:2048] or None,
        "user_agent": (item.get("user_agent") or "")[:512] or None,
        "response_code": item.get("rsp_code") or item.get("response_code"),
        "primary_signature": item.get("violation_name") or item.get("primary_signature"),
        "signature_ids": item.get("violation_ids") or item.get("signature_ids"),
        "threat_categories": item.get("threat_categories"),
        "severity": item.get("severity"),
        "waf_policy_namespace": waf_policy.get("namespace") if isinstance(waf_policy, dict) else None,
        "waf_policy_name": waf_policy.get("name") if isinstance(waf_policy, dict) else None,
        "raw_event": item,
    }


_METRIC_TO_COLUMN = {
    "loadbalancer.request_count": "request_count",
    "loadbalancer.waf_blocked_count": "blocked_count",
    "loadbalancer.waf_monitored_count": "monitored_count",
    "loadbalancer.error_count": "error_count",
}


def extract_metric_buckets(
    payload: dict[str, Any], *, lb_namespace: str, lb_name: str
) -> dict[datetime, dict[str, int]]:
    """Flatten F5 XC metrics_multi_v2 shape to {bucket_time: {col: count, ...}}.

    F5 XC returns:
      data: [
        {metric: "loadbalancer.request_count", values: [[ts, val], [ts, val]]},
        {metric: "loadbalancer.waf_blocked_count", values: [...]},
        ...
      ]

    Caller upserts per (bucket_time, tenant_id, lb_namespace, lb_name).
    """
    buckets: dict[datetime, dict[str, int]] = {}
    for series in payload.get("data") or []:
        col = _METRIC_TO_COLUMN.get(series.get("metric"))
        if col is None:
            continue
        for entry in series.get("values") or []:
            if not isinstance(entry, list) or len(entry) != 2:
                continue
            ts, val = entry
            bucket = _parse_iso(ts) if isinstance(ts, str) else None
            if bucket is None:
                continue
            try:
                ival = int(val)
            except (TypeError, ValueError):
                continue
            buckets.setdefault(bucket, {})[col] = ival
    # Tag each bucket with the LB info (used by the upsert builder)
    for b in buckets.values():
        b["lb_namespace"] = lb_namespace  # type: ignore[assignment]
        b["lb_name"] = lb_name  # type: ignore[assignment]
    return buckets
