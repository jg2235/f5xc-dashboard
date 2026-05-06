"""Slice 4 — WAF event transformer and metrics extractor tests."""
from __future__ import annotations

from datetime import UTC

from app.f5xc.client import F5XCClient
from app.f5xc.waf_transformers import extract_metric_buckets, extract_waf_event_fields


def test_extract_waf_event_blocked_full_shape() -> None:
    item = {
        "event_time": "2026-04-28T10:30:00Z",
        "namespace": "j-granieri",
        "lb_name": "www-prod-lb",
        "action": "BLOCKED",
        "src_ip": "203.0.113.45",
        "src_country": "RU",
        "src_asn": 13335,
        "method": "POST",
        "url": "/admin",
        "user_agent": "curl/7.68.0",
        "rsp_code": 403,
        "violation_name": "VIOL_SQL_INJECTION",
        "violation_ids": ["VIOL_SQL_INJECTION", "VIOL_HTTP_REQUEST_LENGTH"],
        "threat_categories": ["sql_injection"],
        "severity": "critical",
        "waf_policy": {"namespace": "shared", "name": "owasp-top10-strict"},
    }
    out = extract_waf_event_fields(item, lb_namespace="j-granieri", lb_name="www-prod-lb")
    assert out is not None
    # Action normalised
    assert out["action"] == "BLOCK"
    # Time parsed and tz-aware
    assert out["event_time"].tzinfo is not None
    assert out["event_time"].astimezone(UTC).isoformat().startswith("2026-04-28T10:30:00")
    assert out["source_ip"] == "203.0.113.45"
    assert out["source_country"] == "RU"
    assert out["source_asn"] == 13335
    assert out["primary_signature"] == "VIOL_SQL_INJECTION"
    assert out["severity"] == "critical"
    assert out["waf_policy_namespace"] == "shared"
    assert out["waf_policy_name"] == "owasp-top10-strict"


def test_extract_waf_event_minimal_allow() -> None:
    item = {
        "event_time": "2026-04-28T10:30:00Z",
        "action": "ALLOWED",
        "src_ip": "10.0.0.1",
        "method": "GET",
        "url": "/",
        "rsp_code": 200,
    }
    out = extract_waf_event_fields(item, lb_namespace="j-granieri", lb_name="www-prod-lb")
    assert out is not None
    assert out["action"] == "ALLOW"
    assert out["primary_signature"] is None
    assert out["waf_policy_namespace"] is None


def test_extract_waf_event_bad_timestamp_returns_none() -> None:
    item = {"event_time": "not-a-date", "action": "BLOCK"}
    assert extract_waf_event_fields(item, lb_namespace="x", lb_name="y") is None

    item2 = {"action": "BLOCK"}  # no event_time
    assert extract_waf_event_fields(item2, lb_namespace="x", lb_name="y") is None


def test_extract_waf_event_action_passthrough_unknown() -> None:
    item = {"event_time": "2026-04-28T10:30:00Z", "action": "WEIRD_ACTION"}
    out = extract_waf_event_fields(item, lb_namespace="x", lb_name="y")
    assert out is not None
    assert out["action"] == "WEIRD_ACTION"  # untouched, not lossy


def test_extract_waf_event_long_url_truncated() -> None:
    item = {"event_time": "2026-04-28T10:30:00Z", "url": "x" * 3000}
    out = extract_waf_event_fields(item, lb_namespace="x", lb_name="y")
    assert out is not None
    assert len(out["url"]) == 2048


def test_extract_metric_buckets_full_payload() -> None:
    payload = {
        "data": [
            {
                "metric": "loadbalancer.request_count",
                "values": [["2026-04-28T10:00:00Z", 100], ["2026-04-28T10:01:00Z", 120]],
            },
            {
                "metric": "loadbalancer.waf_blocked_count",
                "values": [["2026-04-28T10:00:00Z", 5], ["2026-04-28T10:01:00Z", 8]],
            },
            {
                "metric": "loadbalancer.waf_monitored_count",
                "values": [["2026-04-28T10:00:00Z", 2]],
            },
            {
                "metric": "loadbalancer.error_count",
                "values": [["2026-04-28T10:00:00Z", 1]],
            },
            # Unknown metric — should be ignored
            {"metric": "loadbalancer.something_else", "values": [["2026-04-28T10:00:00Z", 999]]},
        ]
    }
    buckets = extract_metric_buckets(payload, lb_namespace="j-granieri", lb_name="www-prod-lb")
    keys = sorted(buckets.keys())
    assert len(keys) == 2
    first = buckets[keys[0]]
    assert first["request_count"] == 100
    assert first["blocked_count"] == 5
    assert first["monitored_count"] == 2
    assert first["error_count"] == 1
    second = buckets[keys[1]]
    assert second["request_count"] == 120
    assert second["blocked_count"] == 8
    # Untracked metric should not appear
    assert "something_else" not in first


def test_extract_metric_buckets_malformed_entries_skipped() -> None:
    payload = {
        "data": [
            {
                "metric": "loadbalancer.request_count",
                "values": [
                    ["2026-04-28T10:00:00Z", 100],
                    ["bad-timestamp", 50],
                    ["2026-04-28T10:01:00Z", "not-an-int"],
                    "not-a-list",
                    ["2026-04-28T10:02:00Z", 200],
                ],
            }
        ]
    }
    buckets = extract_metric_buckets(payload, lb_namespace="x", lb_name="y")
    # Only 2 valid entries
    assert len(buckets) == 2


def test_client_get_security_events_mock() -> None:
    c = F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)
    payload = c.get_security_events(
        lb_name="www-prod-lb",
        start_time="2026-04-28T10:00:00Z",
        end_time="2026-04-28T10:10:00Z",
    )
    assert "events" in payload
    # Slice 5 added 80 bot events to this fixture: 80 WAF + 80 bot = 160 total
    assert len(payload["events"]) == 160
    # Sanity check WAF action distribution (looking at all events is fine —
    # bot events are also drawn from {ALLOW, BLOCK, MONITOR, CHALLENGE} set)
    actions = [e["action"] for e in payload["events"]]
    assert "BLOCK" in actions
    assert "ALLOW" in actions
    assert "MONITOR" in actions


def test_client_get_metrics_mock() -> None:
    c = F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)
    payload = c.get_metrics(
        lb_name="www-prod-lb",
        start_time="2026-04-28T10:00:00Z",
        end_time="2026-04-28T11:00:00Z",
    )
    assert "data" in payload
    metric_names = {s["metric"] for s in payload["data"]}
    assert "loadbalancer.request_count" in metric_names
    assert "loadbalancer.waf_blocked_count" in metric_names
    # 24 hours @ 5-min = 288 buckets per metric
    req_series = [s for s in payload["data"] if s["metric"] == "loadbalancer.request_count"][0]
    assert len(req_series["values"]) == 288


def test_client_get_security_events_unknown_lb_returns_empty() -> None:
    c = F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)
    payload = c.get_security_events(
        lb_name="totally-not-a-lb",
        start_time="2026-04-28T10:00:00Z",
        end_time="2026-04-28T10:10:00Z",
    )
    assert payload.get("events") == []
