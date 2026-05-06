"""Slice 5 — bot event transformer, metrics extractor, classifier tests."""
from __future__ import annotations

from datetime import UTC

from app.f5xc.bot_transformers import (
    _confidence_bucket,
    _normalize_bot_category,
    _ua_family,
    extract_bot_event_from_bda,
    extract_bot_event_from_security,
    extract_bot_metric_buckets,
    is_bot_event,
)
from app.f5xc.client import F5XCClient

# ---------------- Helper classifier tests ----------------


def test_ua_family_known_browsers() -> None:
    assert _ua_family("Mozilla/5.0 Chrome/120.0") == "chrome"
    assert _ua_family("Mozilla/5.0 Firefox/121.0") == "firefox"
    assert _ua_family("curl/8.4.0") == "curl"
    assert _ua_family("python-requests/2.31.0") == "python_http"


def test_ua_family_googlebot() -> None:
    assert _ua_family(
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    ) == "googlebot"


def test_ua_family_headless_browser() -> None:
    assert _ua_family(
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 HeadlessChrome/119.0"
    ) == "headless_browser"


def test_ua_family_none_returns_none() -> None:
    assert _ua_family(None) is None
    assert _ua_family("") is None


def test_normalize_bot_category_aliases() -> None:
    assert _normalize_bot_category("verified_search_engine") == "search_engine"
    assert _normalize_bot_category("data_center_bot") == "data_center"
    assert _normalize_bot_category("scraping_bot") == "scraper"
    assert _normalize_bot_category("good") == "good_bot"
    assert _normalize_bot_category(None) == "unknown"
    assert _normalize_bot_category("totally-not-real") == "unknown"


def test_confidence_bucket_thresholds() -> None:
    assert _confidence_bucket(None) == "unknown"
    assert _confidence_bucket(0) == "low"
    assert _confidence_bucket(49) == "low"
    assert _confidence_bucket(50) == "medium"
    assert _confidence_bucket(79) == "medium"
    assert _confidence_bucket(80) == "high"
    assert _confidence_bucket(100) == "high"


# ---------------- Standard BD transformer ----------------


def test_is_bot_event_with_bot_defense_block() -> None:
    assert is_bot_event({"bot_defense": {"action": "CHALLENGE"}})
    assert is_bot_event({"bot_classification": "automation"})
    assert is_bot_event({"bot_score": 75})
    assert not is_bot_event({"action": "BLOCK", "url": "/admin"})


def test_extract_bot_event_from_security_full_shape() -> None:
    item = {
        "event_time": "2026-04-29T10:30:00Z",
        "src_ip": "203.0.113.45",
        "src_country": "RU",
        "src_asn": 13335,
        "method": "POST",
        "url": "/login",
        "user_agent": "python-requests/2.31.0",
        "rsp_code": 403,
        "bot_defense": {
            "action": "BLOCK",
            "bot_classification": "automation",
            "bot_score": 88,
            "challenge": {"type": "js", "result": "failed"},
        },
        "bot_policy": {"namespace": "shared", "name": "global-bot-defense"},
    }
    out = extract_bot_event_from_security(item, lb_namespace="j-granieri", lb_name="www-prod-lb")
    assert out is not None
    assert out["source"] == "standard"
    assert out["action"] == "BLOCK"
    assert out["bot_category"] == "automation"
    assert out["confidence_bucket"] == "high"
    assert out["confidence_score"] == 88
    assert out["ua_family"] == "python_http"
    assert out["source_ip"] == "203.0.113.45"
    assert out["bot_policy_namespace"] == "shared"
    assert out["device_anomalies"] is None  # Standard doesn't have these
    assert out["event_time"].astimezone(UTC).isoformat().startswith("2026-04-29T10:30:00")


def test_extract_bot_event_from_security_minimal_allow() -> None:
    item = {
        "event_time": "2026-04-29T10:30:00Z",
        "bot_defense": {"action": "ALLOW", "bot_classification": "human"},
    }
    out = extract_bot_event_from_security(item, lb_namespace="j-granieri", lb_name="www-prod-lb")
    assert out is not None
    assert out["action"] == "ALLOW"
    assert out["bot_category"] == "human"
    assert out["confidence_bucket"] == "unknown"


# ---------------- BD-A transformer ----------------


def test_extract_bot_event_from_bda_full_shape() -> None:
    item = {
        "event_time": "2026-04-29T10:30:00Z",
        "action": "CHALLENGE",
        "bot_category": "data_center",
        "confidence_score": 92,
        "src_ip": "172.245.18.92",
        "src_country": "US",
        "src_asn": 36352,
        "method": "GET",
        "url": "/api/v2/users",
        "user_agent": "okhttp/4.12.0",
        "challenge": {"type": "captcha", "result": "abandoned"},
        "device_anomalies": ["headless_browser_signature", "tls_fingerprint_mismatch"],
        "bot_policy": {"namespace": "shared", "name": "global-bot-defense"},
    }
    out = extract_bot_event_from_bda(item, lb_namespace="j-granieri", lb_name="api-prod-lb")
    assert out is not None
    assert out["source"] == "bd_advanced"
    assert out["action"] == "CHALLENGE"
    assert out["bot_category"] == "data_center"
    assert out["confidence_bucket"] == "high"
    assert out["confidence_score"] == 92
    assert out["challenge_type"] == "captcha"
    assert out["challenge_result"] == "abandoned"
    assert out["ua_family"] == "language_runtime"
    assert out["device_anomalies"] == ["headless_browser_signature", "tls_fingerprint_mismatch"]


def test_extract_bot_event_from_bda_challenge_with_no_result_defaults_abandoned() -> None:
    item = {
        "event_time": "2026-04-29T10:30:00Z",
        "action": "CHALLENGE",
        "bot_category": "automation",
        "confidence_score": 75,
        # no challenge.result
    }
    out = extract_bot_event_from_bda(item, lb_namespace="x", lb_name="y")
    assert out is not None
    assert out["challenge_result"] == "abandoned"


def test_extract_bot_event_bad_timestamp_returns_none() -> None:
    item = {"event_time": "not-a-date", "bot_category": "automation"}
    assert extract_bot_event_from_bda(item, lb_namespace="x", lb_name="y") is None
    item2 = {"bot_defense": {"action": "BLOCK"}}  # no event_time
    assert extract_bot_event_from_security(item2, lb_namespace="x", lb_name="y") is None


# ---------------- Bot metric extraction ----------------


def test_extract_bot_metric_buckets_full_payload() -> None:
    payload = {
        "data": [
            {
                "metric": "loadbalancer.bot_request_count",
                "values": [["2026-04-29T10:00:00Z", 500], ["2026-04-29T10:01:00Z", 600]],
            },
            {
                "metric": "loadbalancer.bot_challenge_count",
                "values": [["2026-04-29T10:00:00Z", 50]],
            },
            {
                "metric": "loadbalancer.bot_block_count",
                "values": [["2026-04-29T10:00:00Z", 25]],
            },
            {
                "metric": "loadbalancer.bot_allow_count",
                "values": [["2026-04-29T10:00:00Z", 425]],
            },
            # WAF metric — should be ignored by bot extractor
            {
                "metric": "loadbalancer.waf_blocked_count",
                "values": [["2026-04-29T10:00:00Z", 999]],
            },
        ]
    }
    buckets = extract_bot_metric_buckets(payload, lb_namespace="j-granieri", lb_name="www-prod-lb")
    keys = sorted(buckets.keys())
    assert len(keys) == 2
    first = buckets[keys[0]]
    assert first["request_count"] == 500
    assert first["challenge_count"] == 50
    assert first["block_count"] == 25
    assert first["allow_count"] == 425
    # WAF metric should not bleed into bot bucket
    assert "waf_blocked_count" not in first


# ---------------- Client mock fixtures ----------------


def test_client_get_bot_traffic_mock() -> None:
    c = F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)
    payload = c.get_bot_traffic(
        lb_name="api-prod-lb",
        start_time="2026-04-29T10:00:00Z",
        end_time="2026-04-29T10:10:00Z",
    )
    assert "events" in payload
    # 60 BD-A events on api-prod-lb per the slice 5 fixture generation
    assert len(payload["events"]) == 60
    actions = {e["action"] for e in payload["events"]}
    assert "BLOCK" in actions
    assert "CHALLENGE" in actions


def test_client_get_bot_traffic_unknown_lb_returns_empty() -> None:
    c = F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)
    payload = c.get_bot_traffic(
        lb_name="totally-not-a-lb",
        start_time="2026-04-29T10:00:00Z",
        end_time="2026-04-29T10:10:00Z",
    )
    assert payload.get("events") == []


def test_security_events_now_includes_bot_events_on_www_prod() -> None:
    """www-prod-lb's security_events fixture was extended to also include
    bot events (credential stuffing on /login, scraper on /products)."""
    c = F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)
    payload = c.get_security_events(
        lb_name="www-prod-lb",
        start_time="2026-04-29T10:00:00Z",
        end_time="2026-04-29T10:10:00Z",
    )
    # Should be 80 WAF events + 80 bot events = 160 total
    assert len(payload["events"]) == 160
    bot_events = [e for e in payload["events"] if is_bot_event(e)]
    assert len(bot_events) == 80
