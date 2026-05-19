"""WAF analytics transformers (slice 4).

Live in their own module to keep transformers.py from growing further.
F5 XC's security_events shape is documented imprecisely — these defaults
match what the live API has emitted in v0.4 testing, with graceful
fallbacks for missing fields.
"""
from __future__ import annotations

import json as _json
import re as _re
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


def _parse_asn(raw: str | int | None) -> int | None:
    """Parse ASN from int or 'org name(number)' string format."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    m = _re.search(r'\((\d+)\)', str(raw))
    if m:
        return int(m.group(1))
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def extract_waf_event_fields(
    item: dict[str, Any] | str, *, lb_namespace: str, lb_name: str,
) -> dict[str, Any] | None:
    """Flatten an app_security/events record into WafEvent column shape.

    The live API returns each event as a JSON-encoded string; this handles
    both pre-parsed dicts (fixtures/tests) and raw strings from the live API.
    Returns None if event_time can't be parsed.
    """
    if isinstance(item, str):
        try:
            item = _json.loads(item)
        except _json.JSONDecodeError:
            return None

    # Live API: "@timestamp" (ms precision ISO). Fixtures use "event_time".
    event_time = _parse_iso(
        item.get("@timestamp") or item.get("event_time") or item.get("timestamp") or item.get("time")
    )
    if event_time is None:
        return None

    action_raw = (item.get("action") or "").upper()
    action = {
        "BLOCKED": "BLOCK", "BLOCK": "BLOCK",
        "ALLOWED": "ALLOW", "ALLOW": "ALLOW",
        "MONITORED": "MONITOR", "MONITOR": "MONITOR",
    }.get(action_raw, action_raw or "ALLOW")

    # Live API: waf_policy info is in sec_event_name; fixture had a waf_policy dict.
    waf_policy = item.get("waf_policy") or {}
    waf_policy_name = (
        waf_policy.get("name") if isinstance(waf_policy, dict)
        else item.get("sec_event_name")
    )

    return {
        "event_time": event_time,
        "lb_namespace": lb_namespace,
        "lb_name": lb_name,
        "action": action,
        "source_ip": item.get("src_ip") or item.get("source_ip"),
        # Live API uses "country"; fixtures used "src_country"
        "source_country": item.get("country") or item.get("src_country") or item.get("source_country"),
        # Live API: "asn" is "org name(number)" — extract the integer part.
        "source_asn": _parse_asn(item.get("asn") or item.get("src_asn") or item.get("source_asn")),
        "method": item.get("method"),
        # Live API uses "req_path"; fixtures used "url"
        "url": (item.get("req_path") or item.get("url") or "")[:2048] or None,
        "user_agent": (item.get("user_agent") or "")[:512] or None,
        "response_code": item.get("rsp_code") or item.get("response_code"),
        # Live API uses "sec_event_name"; fixtures used "violation_name"
        "primary_signature": item.get("sec_event_name") or item.get("violation_name") or item.get("primary_signature"),
        "signature_ids": item.get("violation_ids") or item.get("signature_ids"),
        # Live API uses "sec_event_type" as the category
        "threat_categories": item.get("sec_event_type") or item.get("threat_categories"),
        "severity": item.get("severity"),
        "waf_policy_namespace": waf_policy.get("namespace") if isinstance(waf_policy, dict) else lb_namespace,
        "waf_policy_name": waf_policy_name,
        "raw_event": item,
    }


_METRIC_TO_COLUMN = {
    "loadbalancer.request_count": "request_count",
    "loadbalancer.waf_blocked_count": "blocked_count",
    "loadbalancer.waf_monitored_count": "monitored_count",
    "loadbalancer.error_count": "error_count",
}

# app_security/metrics returns flat dicts; these are the live API field names.
_APPSEC_METRIC_COLUMNS = {
    "request_count": "request_count",
    "waf_blocked_count": "blocked_count",
    "waf_monitored_count": "monitored_count",
    "error_count": "error_count",
}


def extract_metric_buckets(
    payload: dict[str, Any], *, lb_namespace: str, lb_name: str
) -> dict[datetime, dict[str, int]]:
    """Flatten F5 XC app_security/metrics (or legacy metrics_multi_v2) to
    {bucket_time: {col: count, ...}}.

    app_security/metrics returns:
      {"data": [{"bucket_time": "...", "request_count": N, "waf_blocked_count": N, ...}], "step": "5m"}

    Legacy metrics_multi_v2 returned:
      {"data": [{"metric": "loadbalancer.request_count", "values": [[ts, val], ...]}, ...]}

    Both shapes are handled; caller upserts per (bucket_time, tenant_id, lb_namespace, lb_name).
    """
    buckets: dict[datetime, dict[str, int]] = {}
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue

        if "metric" in item:
            # Legacy metrics_multi_v2 shape
            col = _METRIC_TO_COLUMN.get(item.get("metric"))
            if col is None:
                continue
            for entry in item.get("values") or []:
                if not isinstance(entry, list) or len(entry) != 2:
                    continue
                ts, val = entry
                bucket = _parse_iso(ts) if isinstance(ts, str) else None
                if bucket is None:
                    continue
                try:
                    buckets.setdefault(bucket, {})[col] = int(val)
                except (TypeError, ValueError):
                    continue
        else:
            # app_security/metrics flat dict shape
            ts = item.get("bucket_time") or item.get("timestamp")
            bucket = _parse_iso(ts) if isinstance(ts, str) else None
            if bucket is None:
                continue
            for src_key, col in _APPSEC_METRIC_COLUMNS.items():
                val = item.get(src_key)
                if val is not None:
                    try:
                        buckets.setdefault(bucket, {})[col] = int(val)
                    except (TypeError, ValueError):
                        pass

    for b in buckets.values():
        b["lb_namespace"] = lb_namespace  # type: ignore[assignment]
        b["lb_name"] = lb_name  # type: ignore[assignment]
    return buckets
