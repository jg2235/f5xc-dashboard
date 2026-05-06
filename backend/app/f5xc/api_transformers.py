"""API discovery + per-endpoint metric transformers (slice 6).

Maps F5 XC's discovery payloads to our model shape, with shadow-endpoint
detection (endpoints discovered by ML but not declared in any
api_definition).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_VALID_AUTH_TYPES = {"none", "basic", "bearer", "oauth", "apikey", "unknown"}
_VALID_DISCOVERY_STATES = {"learning", "mature", "enforcing", "disabled", "unknown"}


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


def _normalize_auth_type(raw: str | None) -> str | None:
    if not raw:
        return None
    r = raw.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "no_auth": "none",
        "anonymous": "none",
        "http_basic": "basic",
        "http_bearer": "bearer",
        "jwt": "bearer",
        "api_key": "apikey",
        "oauth2": "oauth",
        "oauth_2": "oauth",
    }
    r = aliases.get(r, r)
    return r if r in _VALID_AUTH_TYPES else "unknown"


def _normalize_discovery_state(raw: str | None) -> str:
    if not raw:
        return "unknown"
    r = raw.strip().lower()
    aliases = {
        "in_learning": "learning",
        "matured": "mature",
        "enforce": "enforcing",
        "active": "enforcing",
        "off": "disabled",
        "stopped": "disabled",
    }
    r = aliases.get(r, r)
    return r if r in _VALID_DISCOVERY_STATES else "unknown"


def extract_api_endpoint(
    item: dict[str, Any],
    *,
    declared_endpoints: set[tuple[str, str]] | None = None,
) -> dict[str, Any] | None:
    """Flatten a discovered endpoint record into ApiEndpoint column shape.

    `declared_endpoints` is a set of (method, path) tuples for endpoints
    explicitly declared in any api_definition the LB references. Used to
    populate the `is_shadow` flag.

    Returns None if method or path are missing (record is unusable).
    """
    method = (item.get("method") or item.get("http_method") or "").upper().strip()
    path = (item.get("path") or item.get("endpoint") or item.get("url") or "").strip()
    if not method or not path:
        return None

    # Truncate path to schema limit
    if len(path) > 2048:
        path = path[:2048]

    declared = declared_endpoints or set()
    is_shadow = (method, path) not in declared

    api_def = item.get("api_definition") or {}
    if not isinstance(api_def, dict):
        api_def = {}

    confidence = item.get("discovery_confidence") or item.get("confidence")
    if isinstance(confidence, str):
        try:
            confidence = int(confidence)
        except ValueError:
            confidence = None
    elif not isinstance(confidence, int):
        confidence = None

    samples = item.get("total_request_samples") or item.get("sample_count") or 0
    try:
        samples = int(samples)
    except (TypeError, ValueError):
        samples = 0

    response_codes = item.get("response_codes") or item.get("observed_response_codes")
    if not isinstance(response_codes, list):
        response_codes = None
    else:
        try:
            response_codes = [int(c) for c in response_codes if c is not None]
        except (TypeError, ValueError):
            response_codes = None

    return {
        "method": method,
        "endpoint_path": path,
        "is_shadow": is_shadow,
        "api_definition_namespace": api_def.get("namespace") if not is_shadow else None,
        "api_definition_name": api_def.get("name") if not is_shadow else None,
        "discovery_confidence": confidence,
        "total_request_samples": samples,
        "last_seen_at": _parse_iso(item.get("last_seen") or item.get("last_seen_at")),
        "first_seen_at": _parse_iso(item.get("first_seen") or item.get("first_seen_at")),
        "response_codes": response_codes,
        "query_params": item.get("query_params") if isinstance(item.get("query_params"), list) else None,
        "body_params": item.get("body_params") if isinstance(item.get("body_params"), list) else None,
        "auth_type": _normalize_auth_type(item.get("auth_type") or item.get("authentication")),
    }


def extract_discovery_state(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten F5 XC's discovery state payload into ApiDiscoveryState shape."""
    state = _normalize_discovery_state(payload.get("state"))

    confidence = payload.get("confidence_score") or payload.get("confidence")
    if isinstance(confidence, str):
        try:
            confidence = int(confidence)
        except ValueError:
            confidence = None
    elif not isinstance(confidence, int):
        confidence = None

    endpoints = payload.get("total_endpoints_discovered") or payload.get("endpoint_count") or 0
    samples = payload.get("total_traffic_samples") or payload.get("sample_count") or 0
    try:
        endpoints = int(endpoints)
    except (TypeError, ValueError):
        endpoints = 0
    try:
        samples = int(samples)
    except (TypeError, ValueError):
        samples = 0

    return {
        "state": state,
        "confidence_score": confidence,
        "total_endpoints_discovered": endpoints,
        "total_traffic_samples": samples,
        "last_learning_update": _parse_iso(
            payload.get("last_learning_update") or payload.get("last_update")
        ),
        "state_changed_at": _parse_iso(
            payload.get("state_changed_at") or payload.get("state_transition_at")
        ),
    }


# ---------------------------------------------------------------------------
# Per-endpoint metrics extraction
# ---------------------------------------------------------------------------
_API_METRIC_COLUMN = {
    "loadbalancer.request_count": "request_count",
    "loadbalancer.http_4xx_count": "error_4xx_count",
    "loadbalancer.http_5xx_count": "error_5xx_count",
    "loadbalancer.latency_p50": "latency_p50_ms",
    "loadbalancer.latency_p95": "latency_p95_ms",
    "loadbalancer.latency_p99": "latency_p99_ms",
}


def extract_api_endpoint_metric_buckets(
    payload: dict[str, Any], *, lb_namespace: str, lb_name: str,
) -> dict[tuple[datetime, str, str], dict[str, Any]]:
    """Flatten F5 XC's grouped metrics_multi_v2 response into upsert-ready dicts.

    Returns:
      {
        (bucket_time, method, endpoint_path): {
          "request_count": int, "error_4xx_count": int, ...,
          "latency_p50_ms": float | None, "latency_p95_ms": float | None,
          "latency_p99_ms": float | None,
          "lb_namespace": str, "lb_name": str,
        },
        ...
      }

    Caller upserts per-bucket-per-endpoint into api_metrics_1min.

    F5 XC group_by response shape (per series):
      {
        "metric": "loadbalancer.request_count",
        "labels": {"method": "GET", "endpoint": "/api/v2/users"},
        "values": [["<iso>", val], ...]
      }
    """
    out: dict[tuple[datetime, str, str], dict[str, Any]] = {}
    is_latency = {"latency_p50_ms", "latency_p95_ms", "latency_p99_ms"}

    for series in payload.get("data") or []:
        col = _API_METRIC_COLUMN.get(series.get("metric"))
        if col is None:
            continue
        labels = series.get("labels") or {}
        method = (labels.get("method") or "").upper().strip()
        endpoint = (labels.get("endpoint") or labels.get("path") or "").strip()
        if not method or not endpoint:
            continue
        if len(endpoint) > 2048:
            endpoint = endpoint[:2048]

        for entry in series.get("values") or []:
            if not isinstance(entry, list) or len(entry) != 2:
                continue
            ts, val = entry
            bucket = _parse_iso(ts) if isinstance(ts, str) else None
            if bucket is None:
                continue
            key = (bucket, method, endpoint)
            target = out.setdefault(key, {
                "lb_namespace": lb_namespace,
                "lb_name": lb_name,
            })
            if col in is_latency:
                try:
                    target[col] = float(val)
                except (TypeError, ValueError):
                    target[col] = None
            else:
                try:
                    target[col] = int(val)
                except (TypeError, ValueError):
                    target[col] = 0
    return out
