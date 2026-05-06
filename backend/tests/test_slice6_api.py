"""Slice 6 — API discovery transformer + client tests."""
from __future__ import annotations

from datetime import UTC

from app.f5xc.api_transformers import (
    _normalize_auth_type,
    _normalize_discovery_state,
    extract_api_endpoint,
    extract_api_endpoint_metric_buckets,
    extract_discovery_state,
)
from app.f5xc.client import F5XCClient
from app.f5xc.transformers import extract_api_definition_fields

# ---------------- Helper classifier tests ----------------


def test_normalize_auth_type_aliases() -> None:
    assert _normalize_auth_type("none") == "none"
    assert _normalize_auth_type("Bearer") == "bearer"
    assert _normalize_auth_type("HTTP-BASIC") == "basic"
    assert _normalize_auth_type("api-key") == "apikey"
    assert _normalize_auth_type("oauth2") == "oauth"
    assert _normalize_auth_type("jwt") == "bearer"
    assert _normalize_auth_type(None) is None
    assert _normalize_auth_type("totally-not-real") == "unknown"


def test_normalize_discovery_state_aliases() -> None:
    assert _normalize_discovery_state("learning") == "learning"
    assert _normalize_discovery_state("MATURE") == "mature"
    assert _normalize_discovery_state("matured") == "mature"
    assert _normalize_discovery_state("active") == "enforcing"
    assert _normalize_discovery_state("off") == "disabled"
    assert _normalize_discovery_state(None) == "unknown"
    assert _normalize_discovery_state("garbage") == "unknown"


# ---------------- Endpoint transformer ----------------


def test_extract_api_endpoint_full_shape_declared() -> None:
    item = {
        "method": "POST",
        "path": "/api/v2/users",
        "discovery_confidence": 92,
        "total_request_samples": 14523,
        "last_seen": "2026-04-29T18:00:00Z",
        "first_seen": "2026-01-15T00:00:00Z",
        "auth_type": "bearer",
        "response_codes": [201, 400, 401],
        "query_params": [{"name": "page", "type": "integer"}],
        "body_params": [{"name": "name", "type": "string", "required": True}],
        "api_definition": {"namespace": "shared", "name": "public-api-v2-spec"},
    }
    declared = {("POST", "/api/v2/users"), ("GET", "/api/v2/users")}
    out = extract_api_endpoint(item, declared_endpoints=declared)
    assert out is not None
    assert out["method"] == "POST"
    assert out["endpoint_path"] == "/api/v2/users"
    assert out["is_shadow"] is False
    assert out["api_definition_name"] == "public-api-v2-spec"
    assert out["discovery_confidence"] == 92
    assert out["total_request_samples"] == 14523
    assert out["last_seen_at"].astimezone(UTC).isoformat().startswith("2026-04-29T18:00:00")
    assert out["auth_type"] == "bearer"
    assert out["response_codes"] == [201, 400, 401]


def test_extract_api_endpoint_shadow_when_not_declared() -> None:
    item = {"method": "GET", "path": "/api/v2/admin/secret"}
    declared = {("POST", "/api/v2/users")}
    out = extract_api_endpoint(item, declared_endpoints=declared)
    assert out is not None
    assert out["is_shadow"] is True
    assert out["api_definition_name"] is None


def test_extract_api_endpoint_method_uppercased() -> None:
    item = {"method": "post", "path": "/x"}
    out = extract_api_endpoint(item)
    assert out is not None
    assert out["method"] == "POST"


def test_extract_api_endpoint_missing_method_or_path_returns_none() -> None:
    assert extract_api_endpoint({"path": "/x"}) is None
    assert extract_api_endpoint({"method": "GET"}) is None
    assert extract_api_endpoint({}) is None


def test_extract_api_endpoint_long_path_truncated() -> None:
    item = {"method": "GET", "path": "/" + "x" * 3000}
    out = extract_api_endpoint(item)
    assert out is not None
    assert len(out["endpoint_path"]) == 2048


def test_extract_api_endpoint_invalid_response_codes_become_none() -> None:
    item = {"method": "GET", "path": "/x", "response_codes": ["not", "ints"]}
    out = extract_api_endpoint(item)
    assert out is not None
    assert out["response_codes"] is None


# ---------------- Discovery state ----------------


def test_extract_discovery_state_full_shape() -> None:
    payload = {
        "state": "enforcing",
        "confidence_score": 96,
        "total_endpoints_discovered": 15,
        "total_traffic_samples": 245823,
        "last_learning_update": "2026-04-29T14:00:00Z",
        "state_changed_at": "2026-04-08T00:00:00Z",
    }
    out = extract_discovery_state(payload)
    assert out["state"] == "enforcing"
    assert out["confidence_score"] == 96
    assert out["total_endpoints_discovered"] == 15
    assert out["total_traffic_samples"] == 245823
    assert out["last_learning_update"].astimezone(UTC).isoformat().startswith("2026-04-29T14:00:00")


def test_extract_discovery_state_minimal() -> None:
    out = extract_discovery_state({})
    assert out["state"] == "unknown"
    assert out["confidence_score"] is None
    assert out["total_endpoints_discovered"] == 0


def test_extract_discovery_state_string_numbers() -> None:
    payload = {"state": "mature", "confidence_score": "85", "total_traffic_samples": "1000"}
    out = extract_discovery_state(payload)
    assert out["confidence_score"] == 85
    assert out["total_traffic_samples"] == 1000


# ---------------- Per-endpoint metric extraction ----------------


def test_extract_api_endpoint_metric_buckets_full_payload() -> None:
    payload = {
        "data": [
            {
                "metric": "loadbalancer.request_count",
                "labels": {"method": "GET", "endpoint": "/api/v2/users"},
                "values": [["2026-04-29T10:00:00Z", 100], ["2026-04-29T10:01:00Z", 120]],
            },
            {
                "metric": "loadbalancer.http_4xx_count",
                "labels": {"method": "GET", "endpoint": "/api/v2/users"},
                "values": [["2026-04-29T10:00:00Z", 5]],
            },
            {
                "metric": "loadbalancer.latency_p99",
                "labels": {"method": "GET", "endpoint": "/api/v2/users"},
                "values": [["2026-04-29T10:00:00Z", 145.7]],
            },
            # Different endpoint — separate keys
            {
                "metric": "loadbalancer.request_count",
                "labels": {"method": "POST", "endpoint": "/api/v2/orders"},
                "values": [["2026-04-29T10:00:00Z", 50]],
            },
        ]
    }
    buckets = extract_api_endpoint_metric_buckets(
        payload, lb_namespace="j-granieri", lb_name="api-prod-lb",
    )
    assert len(buckets) == 3  # 2 buckets for /users + 1 for /orders
    keys = sorted(buckets.keys(), key=lambda k: (k[0], k[1], k[2]))

    # First /users bucket
    first = buckets[keys[0]]
    assert first["request_count"] == 100
    assert first["error_4xx_count"] == 5
    assert first["latency_p99_ms"] == 145.7
    assert first["lb_name"] == "api-prod-lb"


def test_extract_api_endpoint_metric_buckets_skip_missing_labels() -> None:
    payload = {
        "data": [
            {
                "metric": "loadbalancer.request_count",
                "labels": {},  # no method/endpoint
                "values": [["2026-04-29T10:00:00Z", 100]],
            },
        ]
    }
    buckets = extract_api_endpoint_metric_buckets(
        payload, lb_namespace="x", lb_name="y",
    )
    assert len(buckets) == 0


def test_extract_api_endpoint_metric_buckets_unknown_metric_ignored() -> None:
    payload = {
        "data": [
            {
                "metric": "loadbalancer.weird_metric",
                "labels": {"method": "GET", "endpoint": "/x"},
                "values": [["2026-04-29T10:00:00Z", 100]],
            },
        ]
    }
    buckets = extract_api_endpoint_metric_buckets(
        payload, lb_namespace="x", lb_name="y",
    )
    assert len(buckets) == 0


# ---------------- ApiDefinition declared_endpoints extraction ----------------


def test_api_definition_declared_endpoints_from_openapi() -> None:
    item = {
        "namespace": "shared",
        "name": "public-api-v2-spec",
        "get_spec": {
            "api_specs": [
                {
                    "openapi_spec": {
                        "paths": {
                            "/api/v2/users": {
                                "get": {"summary": "list"},
                                "post": {"summary": "create"},
                            },
                            "/api/v2/orders": {
                                "get": {"summary": "list"},
                            },
                        },
                    },
                },
            ],
        },
    }
    out = extract_api_definition_fields(item)
    declared = out["declared_endpoints"]
    assert declared is not None
    methods_paths = {(d["method"], d["path"]) for d in declared}
    assert methods_paths == {
        ("GET", "/api/v2/users"),
        ("POST", "/api/v2/users"),
        ("GET", "/api/v2/orders"),
    }
    assert out["endpoint_count"] == 2  # number of paths


def test_api_definition_no_declared_when_no_paths() -> None:
    item = {"namespace": "x", "name": "y", "get_spec": {"api_specs": []}}
    out = extract_api_definition_fields(item)
    assert out["declared_endpoints"] is None


# ---------------- Client mock fixtures ----------------


def test_client_list_api_endpoints_mock() -> None:
    c = F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)
    items = c.list_api_endpoints(lb_name="api-prod-lb")
    assert len(items) == 15
    methods = {i["method"] for i in items}
    assert "GET" in methods and "POST" in methods


def test_client_list_api_endpoints_unknown_lb_returns_empty() -> None:
    c = F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)
    items = c.list_api_endpoints(lb_name="totally-not-a-lb")
    assert items == []


def test_client_get_api_discovery_state_mock() -> None:
    c = F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)
    payload = c.get_api_discovery_state(lb_name="api-prod-lb")
    assert payload["state"] == "enforcing"
    assert payload["total_endpoints_discovered"] == 15

    legacy = c.get_api_discovery_state(lb_name="legacy-internal-http")
    assert legacy["state"] == "learning"

    unknown = c.get_api_discovery_state(lb_name="totally-not-a-lb")
    assert unknown["state"] == "unknown"


def test_client_get_api_endpoint_metrics_mock() -> None:
    c = F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)
    payload = c.get_api_endpoint_metrics(
        lb_name="api-prod-lb",
        start_time="2026-04-29T10:00:00Z",
        end_time="2026-04-29T11:00:00Z",
    )
    assert "data" in payload
    # 8 endpoints × 6 metrics = 48 series
    assert len(payload["data"]) == 48
    series_metrics = {s["metric"] for s in payload["data"]}
    assert "loadbalancer.request_count" in series_metrics
    assert "loadbalancer.latency_p99" in series_metrics


def test_client_metrics_multi_v2_routes_correctly_by_group_by() -> None:
    """Slice 6 added group_by-aware routing: same URL, different fixture
    based on whether body has group_by (= API metrics) or not (= WAF/bot)."""
    c = F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)
    # Without group_by → WAF/bot fixtures (8 series — 4 WAF + 4 bot)
    waf_payload = c.get_metrics(
        lb_name="www-prod-lb",
        start_time="2026-04-29T10:00:00Z",
        end_time="2026-04-29T11:00:00Z",
    )
    waf_metrics = {s["metric"] for s in waf_payload["data"]}
    assert "loadbalancer.waf_blocked_count" in waf_metrics
    # With group_by → API fixtures (per-endpoint series)
    api_payload = c.get_api_endpoint_metrics(
        lb_name="www-prod-lb",
        start_time="2026-04-29T10:00:00Z",
        end_time="2026-04-29T11:00:00Z",
    )
    api_metrics = {s["metric"] for s in api_payload["data"]}
    assert "loadbalancer.latency_p99" in api_metrics
    # Crucially — they're different responses
    assert "loadbalancer.waf_blocked_count" not in api_metrics
