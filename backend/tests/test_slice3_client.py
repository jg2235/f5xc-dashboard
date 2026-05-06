"""Slice 3 F5XCClient tests — policies endpoints with namespace fixtures."""
from __future__ import annotations

import pytest

from app.f5xc.client import F5XCClient


def _client() -> F5XCClient:
    return F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)


def test_list_app_firewalls_shared() -> None:
    items = _client().list_policies("app_firewall", "shared")
    names = {i["name"] for i in items}
    assert "owasp-top10-strict" in names
    assert "api-protection-strict" in names


def test_list_app_firewalls_local() -> None:
    items = _client().list_policies("app_firewall", "j-granieri")
    names = {i["name"] for i in items}
    assert "dev-monitoring-only" in names


def test_list_service_policies_namespaced() -> None:
    shared = _client().list_policies("service_policy", "shared")
    local = _client().list_policies("service_policy", "j-granieri")
    assert {i["name"] for i in shared} == {"global-blocklist"}
    assert {i["name"] for i in local} == {"geo-block-policy"}


def test_list_bot_defense_policies_local_empty() -> None:
    local = _client().list_policies("bot_defense_policy", "j-granieri")
    assert local == []
    shared = _client().list_policies("bot_defense_policy", "shared")
    assert {i["name"] for i in shared} == {"global-bot-defense"}


def test_list_api_definitions_both_namespaces() -> None:
    shared = _client().list_policies("api_definition", "shared")
    local = _client().list_policies("api_definition", "j-granieri")
    # Slice 6 added ecommerce-checkout-api to support shadow-endpoint demo on www-prod-lb
    assert {i["name"] for i in shared} == {"public-api-v2-spec", "ecommerce-checkout-api"}
    assert {i["name"] for i in local} == {"internal-api-spec"}


def test_unknown_policy_type_raises() -> None:
    with pytest.raises(ValueError):
        _client().list_policies("nonexistent_thing", "shared")


def test_list_policies_unknown_namespace_returns_empty() -> None:
    items = _client().list_policies("app_firewall", "totally-not-a-namespace")
    assert items == []
