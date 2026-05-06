"""Slice 3 transformer tests — policy extractors and LB→policy attachment."""
from __future__ import annotations

from app.f5xc.transformers import (
    extract_api_definition_fields,
    extract_app_firewall_fields,
    extract_bot_defense_policy_fields,
    extract_lb_policy_attachments,
    extract_service_policy_fields,
)


def test_extract_app_firewall_blocking_with_violation_settings() -> None:
    item = {
        "name": "owasp-top10-strict",
        "namespace": "shared",
        "get_spec": {
            "blocking": {},
            "violation_settings": {
                "owasp_top10": {"action": "BLOCK"},
                "credit_card_data": {"action": "BLOCK"},
                "ssn_data": {"action": "MONITOR"},
            },
            "blocking_settings": {
                "sql_injection": {"action": "BLOCK"},
                "cross_site_scripting": {"action": "BLOCK"},
                "path_traversal": {"action": "BLOCK"},
                "broken_auth": {"action": "MONITOR"},
            },
            "exclusion_rules": [{"path": {"prefix": "/health"}}],
            "allowed_response_codes": {"response_code": [200, 201, 404]},
        },
    }
    out = extract_app_firewall_fields(item)
    assert out["enforcement_mode"] == "blocking"
    assert out["is_shared"] is True
    assert "owasp_top10" in out["enabled_signature_categories"]
    assert "ssn_data" in out["enabled_signature_categories"]
    # MONITOR should NOT be in blocked_attack_types
    assert "broken_auth" not in out["blocked_attack_types"]
    assert "sql_injection" in out["blocked_attack_types"]
    assert "cross_site_scripting" in out["blocked_attack_types"]
    assert out["exclusion_rule_count"] == 1
    assert out["allowed_response_codes"] == [200, 201, 404]


def test_extract_app_firewall_monitoring_local() -> None:
    item = {
        "name": "dev-monitor",
        "namespace": "j-granieri",
        "get_spec": {"monitoring": {}, "violation_settings": {}, "blocking_settings": {}},
    }
    out = extract_app_firewall_fields(item)
    assert out["enforcement_mode"] == "monitoring"
    assert out["is_shared"] is False


def test_extract_service_policy_deny_list_with_geo() -> None:
    item = {
        "name": "global-blocklist",
        "namespace": "shared",
        "get_spec": {
            "default_action_choice": {"deny_list": {}},
            "rules": [
                {"simple_rule": {"action": "DENY", "country_list": {"country_codes": ["KP"]}}},
                {"simple_rule": {"action": "DENY", "ip_prefix_list": {"prefixes": ["10.0.0.0/8"]}}},
                {"simple_rule": {"action": "ALLOW", "path": {"prefix": "/health"}}},
            ],
        },
    }
    out = extract_service_policy_fields(item)
    assert out["default_action"] == "DENY"
    assert out["rule_count"] == 3
    assert out["allow_rule_count"] == 1
    assert out["deny_rule_count"] == 2
    assert out["has_geo_rules"] is True
    assert out["has_ip_rules"] is True
    assert out["has_path_rules"] is True
    assert out["is_shared"] is True


def test_extract_bot_defense_policy_mixed_mitigations() -> None:
    item = {
        "name": "bot-shield",
        "namespace": "shared",
        "get_spec": {
            "protected_app_endpoints": [
                {"path": {"prefix": "/login"}, "mitigation": {"js_challenge": {}}},
                {"path": {"prefix": "/signup"}, "mitigation": {"captcha_challenge": {}}},
                {"path": {"exact": "/admin"}, "mitigation": {"block": {}}},
            ],
        },
    }
    out = extract_bot_defense_policy_fields(item)
    assert out["protected_endpoint_count"] == 3
    assert out["has_javascript_challenge"] is True
    assert out["has_captcha_challenge"] is True
    assert out["has_block"] is True
    assert out["has_redirect"] is False
    assert "/login" in out["protected_paths"]
    assert "/admin" in out["protected_paths"]


def test_extract_api_definition_swagger_endpoints() -> None:
    item = {
        "name": "public-api-v2",
        "namespace": "shared",
        "get_spec": {
            "api_specs": [
                {
                    "swagger_spec": {
                        "paths": {"/v2/users": {}, "/v2/orders": {}, "/v2/products": {}}
                    }
                }
            ],
            "validation_rules": [{"name": "strict-mode"}],
        },
    }
    out = extract_api_definition_fields(item)
    assert out["spec_format"] == "swagger"
    assert out["api_specs_count"] == 1
    assert out["endpoint_count"] == 3
    assert out["has_validation_rules"] is True


def test_extract_lb_policy_attachments_full_set() -> None:
    item = {
        "name": "www-prod-lb",
        "namespace": "j-granieri",
        "get_spec": {
            "app_firewall": {"namespace": "shared", "name": "owasp-top10-strict"},
            "active_service_policies": {
                "policies": [
                    {"namespace": "j-granieri", "name": "geo-block-policy"},
                    {"namespace": "shared", "name": "global-blocklist"},
                ]
            },
            "bot_defense": {"ref": {"namespace": "shared", "name": "global-bot-defense"}},
            "api_definition": {
                "api_definitions": [
                    {"namespace": "shared", "name": "public-api-v2"}
                ]
            },
        },
    }
    attachments = extract_lb_policy_attachments(item)
    by_type = {(a["policy_type"], a["policy_namespace"], a["policy_name"]) for a in attachments}
    assert ("app_firewall", "shared", "owasp-top10-strict") in by_type
    assert ("service_policy", "j-granieri", "geo-block-policy") in by_type
    assert ("service_policy", "shared", "global-blocklist") in by_type
    assert ("bot_defense_policy", "shared", "global-bot-defense") in by_type
    assert ("api_definition", "shared", "public-api-v2") in by_type


def test_extract_lb_policy_attachments_empty_lb() -> None:
    item = {"name": "legacy", "namespace": "j-granieri", "get_spec": {"http": {"port": 80}}}
    assert extract_lb_policy_attachments(item) == []
