"""Slice 2 F5XCClient tests — sites and origin health endpoints."""
from __future__ import annotations

from app.f5xc.client import F5XCClient


def _client() -> F5XCClient:
    return F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)


def test_list_sites_mock() -> None:
    sites = _client().list_sites()
    names = {s["name"] for s in sites}
    assert {"ny8-nyc", "sv10-sjc", "nyc1-site"}.issubset(names)


def test_origin_health_www_pool_ny() -> None:
    payload = _client().get_origin_health(
        pool_name="www-origin-pool", site_name="ny8-nyc"
    )
    items = payload["items"]
    assert len(items) == 2
    assert all(i["status"] == "HEALTHY" for i in items)


def test_origin_health_www_pool_sv_has_unhealthy() -> None:
    payload = _client().get_origin_health(
        pool_name="www-origin-pool", site_name="sv10-sjc"
    )
    statuses = {i["address"]: i["status"] for i in payload["items"]}
    assert statuses["203.0.113.10"] == "HEALTHY"
    assert statuses["203.0.113.11"] == "UNHEALTHY"


def test_origin_health_api_pool_sv_mixed() -> None:
    payload = _client().get_origin_health(
        pool_name="api-origin-pool", site_name="sv10-sjc"
    )
    statuses = {i["address"]: i["status"] for i in payload["items"]}
    assert statuses["10.0.1.20"] == "HEALTHY"
    assert statuses["10.0.1.21"] == "STARTING"
    assert statuses["10.0.1.22"] == "DRAINING"


def test_origin_health_unknown_pool_falls_back() -> None:
    payload = _client().get_origin_health(
        pool_name="never-existed", site_name="ny8-nyc"
    )
    assert payload["items"] == []
