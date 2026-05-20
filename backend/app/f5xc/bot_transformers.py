"""Bot event transformers (slice 5).

Handles two distinct ingestion paths:

  - Standard BD: events come through security_events with `bot_defense` and
    `bot_classification` fields. The same security_events response feeds both
    sync_waf_events (for WAF events) and sync_bot_events (for bot events) —
    we filter by event type.

  - BD Advanced: events come through bot_traffic endpoint with much richer
    per-decision data (confidence_score, device_anomalies, challenge_result).

Both paths produce BotEvent rows with `source` discriminator + nullable
fields for source-specific data.
"""
from __future__ import annotations

import json as _json
import re
from datetime import UTC, datetime
from typing import Any


def _parse_json_event(item: dict[str, Any] | str) -> dict[str, Any]:
    """Ensure item is a dict — live API returns events as JSON strings."""
    if isinstance(item, str):
        try:
            return _json.loads(item)
        except _json.JSONDecodeError:
            return {}
    return item


def _parse_asn(raw: str | int | None) -> int | None:
    """Parse ASN from int or 'org name(number)' string format."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    m = re.search(r'\((\d+)\)', str(raw))
    if m:
        return int(m.group(1))
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None

# UA family extraction — collapses high-cardinality UA strings into ~12 buckets
_UA_PATTERNS = [
    (re.compile(r"Googlebot|Google-InspectionTool|AdsBot-Google", re.I), "googlebot"),
    (re.compile(r"bingbot|Bingbot", re.I), "bingbot"),
    (re.compile(r"DuckDuckBot|Slurp|Yandex|Baiduspider", re.I), "search_other"),
    (re.compile(r"curl/", re.I), "curl"),
    (re.compile(r"Wget/", re.I), "wget"),
    (re.compile(r"python-requests/|aiohttp/|urllib", re.I), "python_http"),
    (re.compile(r"Go-http-client|okhttp/|Java/|Apache-HttpClient", re.I), "language_runtime"),
    (re.compile(r"PostmanRuntime|Insomnia/|Thunder Client", re.I), "api_tool"),
    (re.compile(r"HeadlessChrome|PhantomJS|Selenium|Puppeteer|Playwright", re.I), "headless_browser"),
    (re.compile(r"Mozilla.*Chrome/", re.I), "chrome"),
    (re.compile(r"Mozilla.*Firefox/", re.I), "firefox"),
    (re.compile(r"Mozilla.*Safari/.*Version/", re.I), "safari"),
    (re.compile(r"Mozilla.*Edg/", re.I), "edge"),
]


def _ua_family(ua: str | None) -> str | None:
    if not ua:
        return None
    for pattern, label in _UA_PATTERNS:
        if pattern.search(ua):
            return label
    # Generic fallback — first slash-separated token
    if "/" in ua:
        return ua.split("/", 1)[0][:64].lower()
    return ua[:64].lower()


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


_VALID_BOT_CATEGORIES = {
    "good_bot", "bad_bot", "automation", "scraper",
    "data_center", "search_engine", "suspicious", "human", "unknown",
}


def _normalize_bot_category(raw: str | None) -> str:
    """F5 XC uses different category naming across BD Standard vs BD-A.
    Map them to our taxonomy."""
    if not raw:
        return "unknown"
    r = raw.strip().lower().replace("-", "_").replace(" ", "_")
    # F5 XC uses these labels on BD-A:
    aliases = {
        # BD-A labels
        "search_engine_bot": "search_engine",
        "good": "good_bot",
        "bad": "bad_bot",
        "verified_search_engine": "search_engine",
        "data_center_bot": "data_center",
        "datacenter": "data_center",
        "datacenter_bot": "data_center",
        "automated_browser": "automation",
        "headless_browser": "automation",
        "scraping_bot": "scraper",
        # Live API: bot_defense.automation_type values
        "token_missing": "bad_bot",
        "automation_tools": "automation",
        "credential_stuffing": "bad_bot",
        "account_takeover": "bad_bot",
        "web_scraper": "scraper",
        "web_scraping": "scraper",
        "data_center": "data_center",
        # Live API: bot_defense.insight values
        "malicious": "bad_bot",
        "benign": "good_bot",
        "suspicious": "suspicious",
        "good_bot": "good_bot",
        # sec_event_name fallback
        "bot_defense_violation": "bad_bot",
    }
    r = aliases.get(r, r)
    return r if r in _VALID_BOT_CATEGORIES else "unknown"


def _confidence_bucket(score: int | None) -> str:
    if score is None:
        return "unknown"
    if score >= 80:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _action_normalize(raw: str | None) -> str:
    if not raw:
        return "ALLOW"
    r = raw.strip().upper()
    return {
        "BLOCKED": "BLOCK",
        "ALLOWED": "ALLOW",
        "MONITORED": "MONITOR",
        "CHALLENGED": "CHALLENGE",
        "JS_CHALLENGE": "CHALLENGE",
        "CAPTCHA_CHALLENGE": "CHALLENGE",
    }.get(r, r) if r in {
        "ALLOW", "BLOCK", "CHALLENGE", "MONITOR",
        "ALLOWED", "BLOCKED", "MONITORED", "CHALLENGED",
        "JS_CHALLENGE", "CAPTCHA_CHALLENGE",
    } else "ALLOW"


def is_bot_event(item: dict[str, Any] | str) -> bool:
    """Filter for security_events records that are actually bot events."""
    item = _parse_json_event(item)
    return bool(
        item.get("sec_event_type") == "bot_defense_sec_event"
        or item.get("bot_defense")
        or item.get("bot_classification")
        or item.get("bot_category")
        or item.get("bot_score")
    )


def extract_bot_event_from_security(
    item: dict[str, Any] | str, *, lb_namespace: str, lb_name: str,
) -> dict[str, Any] | None:
    """Standard BD events from app_security/events."""
    item = _parse_json_event(item)
    # Live API: "@timestamp"; fixtures: "event_time"
    event_time = _parse_iso(
        item.get("@timestamp") or item.get("event_time") or item.get("timestamp") or item.get("time")
    )
    if event_time is None:
        return None

    bot_block = item.get("bot_defense") or {}
    if not isinstance(bot_block, dict):
        bot_block = {}

    action = _action_normalize(
        bot_block.get("action") or item.get("action") or "ALLOW"
    )
    # Live API: automation_type (e.g. "Token Missing") and insight ("MALICIOUS")
    bot_category = _normalize_bot_category(
        bot_block.get("bot_classification")
        or bot_block.get("automation_type")
        or bot_block.get("insight")
        or item.get("bot_classification")
        or item.get("bot_category")
        or item.get("sec_event_name"),
    )
    score = bot_block.get("bot_score") or item.get("bot_score")
    if isinstance(score, str):
        try:
            score = int(score)
        except ValueError:
            score = None
    elif not isinstance(score, int):
        score = None

    challenge_result = "not_issued"
    challenge_type = None
    if action == "CHALLENGE":
        ch = bot_block.get("challenge") or {}
        if isinstance(ch, dict):
            challenge_type = ch.get("type")
            outcome = ch.get("result")
            challenge_result = str(outcome).lower() if outcome else "abandoned"

    bot_policy = item.get("bot_policy") or bot_block.get("policy") or {}
    if not isinstance(bot_policy, dict):
        bot_policy = {}

    ua = item.get("user_agent")
    return {
        "event_time": event_time,
        "lb_namespace": lb_namespace,
        "lb_name": lb_name,
        "source": "standard",
        "action": action,
        "bot_category": bot_category,
        "confidence_bucket": _confidence_bucket(score),
        "confidence_score": score,
        "challenge_result": challenge_result,
        "challenge_type": challenge_type,
        "device_anomalies": None,
        "source_ip": item.get("src_ip") or item.get("source_ip"),
        # Live API: "country"; fixtures: "src_country"
        "source_country": item.get("country") or item.get("src_country") or item.get("source_country"),
        "source_asn": _parse_asn(item.get("asn") or item.get("src_asn") or item.get("source_asn")),
        "method": item.get("method"),
        # Live API: "req_path"; fixtures: "url"
        "endpoint_path": (item.get("req_path") or item.get("url") or "")[:2048] or None,
        "user_agent": (ua or "")[:512] or None,
        "ua_family": _ua_family(ua),
        "bot_policy_namespace": bot_policy.get("namespace") or lb_namespace,
        "bot_policy_name": bot_policy.get("name") or item.get("sec_event_name"),
        "raw_event": item,
    }


def extract_bot_event_from_bda(
    item: dict[str, Any] | str, *, lb_namespace: str, lb_name: str,
) -> dict[str, Any] | None:
    """BD-A events — richer fields when available."""
    item = _parse_json_event(item)
    event_time = _parse_iso(
        item.get("@timestamp") or item.get("event_time") or item.get("timestamp") or item.get("time")
    )
    if event_time is None:
        return None

    action = _action_normalize(item.get("action") or "ALLOW")
    bot_category = _normalize_bot_category(
        item.get("bot_category") or item.get("classification"),
    )
    score = item.get("confidence_score") or item.get("bot_score")
    if isinstance(score, str):
        try:
            score = int(score)
        except ValueError:
            score = None
    elif not isinstance(score, int):
        score = None

    challenge = item.get("challenge") or {}
    if isinstance(challenge, dict):
        ch_type = challenge.get("type") or item.get("challenge_type")
        ch_result_raw = challenge.get("result") or item.get("challenge_result")
    else:
        ch_type = item.get("challenge_type")
        ch_result_raw = item.get("challenge_result")

    if action == "CHALLENGE" and not ch_result_raw:
        challenge_result = "abandoned"
    elif ch_result_raw:
        challenge_result = str(ch_result_raw).lower()
        if challenge_result not in {"passed", "failed", "abandoned", "not_issued"}:
            challenge_result = "not_issued"
    else:
        challenge_result = "not_issued"

    anomalies = item.get("device_anomalies") or item.get("device_fingerprint_anomalies")
    if not isinstance(anomalies, list):
        anomalies = None

    bot_policy = item.get("bot_policy") or {}
    if not isinstance(bot_policy, dict):
        bot_policy = {}

    ua = item.get("user_agent")
    return {
        "event_time": event_time,
        "lb_namespace": lb_namespace,
        "lb_name": lb_name,
        "source": "bd_advanced",
        "action": action,
        "bot_category": bot_category,
        "confidence_bucket": _confidence_bucket(score),
        "confidence_score": score,
        "challenge_result": challenge_result,
        "challenge_type": ch_type,
        "device_anomalies": anomalies,
        "source_ip": item.get("src_ip") or item.get("source_ip"),
        "source_country": item.get("country") or item.get("src_country") or item.get("source_country"),
        "source_asn": _parse_asn(item.get("asn") or item.get("src_asn") or item.get("source_asn")),
        "method": item.get("method"),
        "endpoint_path": (item.get("req_path") or item.get("url") or item.get("endpoint") or "")[:2048] or None,
        "user_agent": (ua or "")[:512] or None,
        "ua_family": _ua_family(ua),
        "bot_policy_namespace": bot_policy.get("namespace"),
        "bot_policy_name": bot_policy.get("name"),
        "raw_event": item,
    }


# ---------------------------------------------------------------------------
# Bot metrics
# ---------------------------------------------------------------------------
_BOT_METRIC_TO_COLUMN = {
    "loadbalancer.bot_request_count": "request_count",
    "loadbalancer.bot_challenge_count": "challenge_count",
    "loadbalancer.bot_block_count": "block_count",
    "loadbalancer.bot_allow_count": "allow_count",
}


def extract_bot_metric_buckets(
    payload: dict[str, Any], *, lb_namespace: str, lb_name: str,
) -> dict[datetime, dict[str, int]]:
    """Flatten F5 XC metrics_multi_v2 bot metrics → {bucket_time: {col: count}}.

    Mirrors extract_metric_buckets() for WAF, just with bot metric names.
    """
    buckets: dict[datetime, dict[str, int]] = {}
    for series in payload.get("data") or []:
        col = _BOT_METRIC_TO_COLUMN.get(series.get("metric"))
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
    for b in buckets.values():
        b["lb_namespace"] = lb_namespace  # type: ignore[assignment]
        b["lb_name"] = lb_name  # type: ignore[assignment]
    return buckets
