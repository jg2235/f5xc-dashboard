"""Slice 7 — security correlator + alert rule pure-function tests.

DB-dependent integration tests (correlator + rule eval) require Postgres
and are not in this file — they run in the deployed environment via the
backend container, not in the sandbox. The pure-function tests here cover
the dataclasses, helpers, and rule registration logic.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.config import Settings
from app.security.alerting import (
    AlertCandidate,
    get_enabled_rules,
)
from app.security.correlator import AttackerAggregates, AttackerKey

# ---------------- AttackerAggregates ----------------


def test_attacker_aggregates_total_calc() -> None:
    a = AttackerAggregates()
    a.waf_block = 5
    a.waf_monitor = 2
    a.bot_block = 3
    a.bot_challenge = 7
    a.api_4xx = 1
    assert a.total == 18


def test_attacker_aggregates_top_endpoint_signature() -> None:
    a = AttackerAggregates()
    t = datetime.now(UTC)
    a.add_event_meta(
        lb_namespace="ns", lb_name="lb1",
        endpoint="/login", signature="VIOL_SQLi", event_time=t,
    )
    a.add_event_meta(
        lb_namespace="ns", lb_name="lb1",
        endpoint="/login", signature="VIOL_SQLi", event_time=t,
    )
    a.add_event_meta(
        lb_namespace="ns", lb_name="lb2",
        endpoint="/admin", signature="VIOL_XSS", event_time=t,
    )
    assert a.top_endpoint == "/login"
    assert a.top_signature == "VIOL_SQLi"
    assert len(a.lbs) == 2


def test_attacker_aggregates_first_last_seen() -> None:
    a = AttackerAggregates()
    t1 = datetime(2026, 4, 29, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 4, 29, 11, 0, tzinfo=UTC)
    t3 = datetime(2026, 4, 29, 9, 0, tzinfo=UTC)
    a.add_event_meta(lb_namespace="x", lb_name="y", endpoint=None, signature=None, event_time=t1)
    a.add_event_meta(lb_namespace="x", lb_name="y", endpoint=None, signature=None, event_time=t2)
    a.add_event_meta(lb_namespace="x", lb_name="y", endpoint=None, signature=None, event_time=t3)
    assert a.first_seen == t3
    assert a.last_seen == t2


def test_attacker_aggregates_empty_top_endpoint_returns_none() -> None:
    a = AttackerAggregates()
    assert a.top_endpoint is None
    assert a.top_signature is None


def test_attacker_aggregates_lb_set_unique() -> None:
    a = AttackerAggregates()
    t = datetime.now(UTC)
    a.add_event_meta(lb_namespace="ns", lb_name="lb1", endpoint=None, signature=None, event_time=t)
    a.add_event_meta(lb_namespace="ns", lb_name="lb1", endpoint=None, signature=None, event_time=t)
    a.add_event_meta(lb_namespace="ns", lb_name="lb2", endpoint=None, signature=None, event_time=t)
    assert len(a.lbs) == 2
    assert "ns/lb1" in a.lbs
    assert "ns/lb2" in a.lbs


def test_attacker_key_tuple_shape() -> None:
    k = AttackerKey(source_ip="1.2.3.4", source_asn=1234, source_country="US")
    assert k.as_tuple() == ("1.2.3.4", 1234, "US")
    k2 = AttackerKey(source_ip="1.2.3.4", source_asn=None, source_country=None)
    assert k2.as_tuple() == ("1.2.3.4", None, None)


# ---------------- AlertCandidate ----------------


def test_alert_candidate_default_severity_and_context() -> None:
    c = AlertCandidate(rule_id="x", severity="info", dedupe_key="k", title="t")
    assert c.severity == "info"
    assert c.context == {}
    assert c.description == ""


def test_alert_candidate_full_shape() -> None:
    c = AlertCandidate(
        rule_id="bot.cred_stuffing",
        severity="critical",
        dedupe_key="ip:9.9.9.9",
        title="Suspected credential stuffing",
        description="80% of challenges failed",
        context={"source_ip": "9.9.9.9", "failure_pct": 80.5},
    )
    assert c.rule_id == "bot.cred_stuffing"
    assert c.context["source_ip"] == "9.9.9.9"
    assert c.context["failure_pct"] == 80.5


# ---------------- Rule registration ----------------


def test_get_enabled_rules_default_all_six_enabled() -> None:
    s = Settings()
    rules = get_enabled_rules(s)
    assert len(rules) == 6
    names = {r.__name__ for r in rules}
    assert names == {
        "rule_waf_block_burst",
        "rule_waf_new_attacker",
        "rule_bot_cred_stuffing",
        "rule_api_state_change",
        "rule_api_shadow_emergence",
        "rule_cert_expiry",
    }


def test_get_enabled_rules_disable_two() -> None:
    s = Settings(
        alert_rule_waf_burst_enabled=False,
        alert_rule_bot_cred_stuff_enabled=False,
    )
    rules = get_enabled_rules(s)
    assert len(rules) == 4
    names = {r.__name__ for r in rules}
    assert "rule_waf_block_burst" not in names
    assert "rule_bot_cred_stuffing" not in names


def test_get_enabled_rules_disable_all() -> None:
    s = Settings(
        alert_rule_waf_burst_enabled=False,
        alert_rule_waf_new_attacker_enabled=False,
        alert_rule_bot_cred_stuff_enabled=False,
        alert_rule_api_state_change_enabled=False,
        alert_rule_api_shadow_enabled=False,
        alert_rule_cert_expiry_enabled=False,
    )
    rules = get_enabled_rules(s)
    assert rules == []


# ---------------- Settings sanity ----------------


def test_default_alert_thresholds() -> None:
    s = Settings()
    assert s.alert_waf_block_burst_threshold == 50
    assert s.alert_bot_cred_stuff_min_events == 20
    assert s.alert_bot_cred_stuff_failure_pct == 50.0
    assert s.alert_api_shadow_emergence_samples == 100
    assert s.alert_retention_days == 90
    assert s.security_profile_window_minutes == 1440  # 24h


def test_security_topk_size_default() -> None:
    s = Settings()
    assert s.security_topk_size == 12  # symmetric with waf/bot/api topk
