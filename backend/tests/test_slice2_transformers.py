"""Slice 2 transformer + classifier tests."""
from __future__ import annotations

from app.f5xc.transformers import (
    ALL_RE_SITES_SENTINEL,
    classify_origin_status,
    extract_healthcheck_fields,
    extract_lb_fields,
    extract_pool_fields,
    extract_site_fields,
)


def test_extract_healthcheck_http() -> None:
    item = {
        "name": "jg-hc-arcadia",
        "namespace": "j-granieri",
        "get_spec": {
            "interval": 15,
            "timeout": 3,
            "healthy_threshold": 3,
            "unhealthy_threshold": 1,
            "jitter_percent": 0,
            "http_health_check": {
                "path": "/",
                "use_origin_server_name": {},
                "expected_status_codes": [200],
                "use_http2": False,
            },
        },
    }
    out = extract_healthcheck_fields(item)
    assert out["protocol"] == "http"
    assert out["http_path"] == "/"
    assert out["http_host_header"] == "(origin server name)"
    assert out["http_use_http2"] is False
    assert out["expected_status_codes"] == ["200"]
    assert out["interval_seconds"] == 15
    assert out["timeout_seconds"] == 3
    assert out["healthy_threshold"] == 3
    assert out["unhealthy_threshold"] == 1


def test_extract_healthcheck_tcp_and_host_header() -> None:
    tcp = extract_healthcheck_fields({
        "name": "tcp-hc", "namespace": "ns",
        "get_spec": {"interval": 10, "tcp_health_check": {"send_payload": "ping"}},
    })
    assert tcp["protocol"] == "tcp"
    assert tcp["http_path"] is None
    assert tcp["expected_status_codes"] is None

    explicit = extract_healthcheck_fields({
        "name": "h", "namespace": "ns",
        "get_spec": {"http_health_check": {"path": "/health", "host_header": "api.example.com"}},
    })
    assert explicit["http_host_header"] == "api.example.com"
    assert explicit["http_path"] == "/health"


def test_classify_origin_status_operational() -> None:
    assert classify_origin_status("HEALTHY") == "healthy"
    assert classify_origin_status("UNHEALTHY") == "unhealthy"
    assert classify_origin_status("UNKNOWN") == "warning"
    assert classify_origin_status("STARTING") == "warning"
    assert classify_origin_status("DRAINING") == "info"
    assert classify_origin_status(None) == "unknown"
    assert classify_origin_status("WEIRD_STATE") == "unknown"


def test_extract_lb_fields_advertise_default_vip() -> None:
    item = {
        "name": "lb1",
        "namespace": "ns",
        "get_spec": {
            "domains": ["a.example.com"],
            "https_auto_cert": {},
            "advertise_on_public_default_vip": {},
            "default_route_pools": [{"pool": {"name": "pool-a"}}],
        },
    }
    out = extract_lb_fields(item)
    assert out["advertised_sites"] == [ALL_RE_SITES_SENTINEL]
    assert out["origin_pool_refs"] == ["pool-a"]


def test_extract_lb_fields_advertise_custom_with_sites() -> None:
    item = {
        "name": "lb2",
        "namespace": "ns",
        "get_spec": {
            "http": {"port": 80},
            "advertise_custom": {
                "advertise_where": [
                    {"site": {"site": {"name": "nyc1"}}},
                    {"site": {"site": {"name": "lax2"}}},
                    {"virtual_site": {"virtual_site": {"name": "all-prod"}}},
                ]
            },
            "default_route_pools": [{"pool": {"name": "pool-b"}}],
        },
    }
    out = extract_lb_fields(item)
    assert out["advertised_sites"] == ["nyc1", "lax2", "virtual:all-prod"]


def test_extract_lb_fields_do_not_advertise() -> None:
    item = {"name": "lb3", "namespace": "ns", "get_spec": {"do_not_advertise": {}}}
    out = extract_lb_fields(item)
    assert out["advertised_sites"] == []


def test_extract_pool_fields_origin_addresses() -> None:
    item = {
        "name": "pool1",
        "namespace": "ns",
        "get_spec": {
            "origin_servers": [
                {"public_ip": {"ip": "1.2.3.4"}},
                {"private_ip": {"ip": "10.0.0.5"}},
                {"public_name": {"dns_name": "origin.example.com"}},
            ],
            "port": 8443,
            "loadbalancer_algorithm": "ROUND_ROBIN",
        },
    }
    out = extract_pool_fields(item)
    assert out["origin_count"] == 3
    assert out["origin_addresses"] == ["1.2.3.4", "10.0.0.5", "origin.example.com"]


def test_extract_site_fields_re() -> None:
    item = {
        "name": "ny8-nyc",
        "get_spec": {"site_type": "RE", "region": "us-east-1", "provider": "ves-io-internal"},
        "system_metadata": {"operational_status": "ONLINE"},
    }
    out = extract_site_fields(item)
    assert out["name"] == "ny8-nyc"
    assert out["site_type"] == "re"
    assert out["region"] == "us-east-1"
    assert out["operational_status"] == "ONLINE"


def test_extract_site_fields_virtual() -> None:
    item = {"name": "all-res", "get_spec": {"site_type": "VIRTUAL_SITE"}}
    assert extract_site_fields(item)["site_type"] == "virtual"


def test_extract_site_fields_unknown() -> None:
    item = {"name": "weird", "get_spec": {"site_type": "MARTIAN"}}
    assert extract_site_fields(item)["site_type"] == "unknown"
