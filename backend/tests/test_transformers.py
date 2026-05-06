"""Pure-function tests for F5 XC transformers + cert classification."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.f5xc.transformers import (
    classify_cert_status,
    extract_cert_fields,
    extract_lb_fields,
    extract_pool_fields,
)


def test_classify_cert_status_thresholds() -> None:
    now = datetime.now(UTC)
    assert classify_cert_status(None, warn_days=30, critical_days=7)[0] == "unknown"
    assert classify_cert_status(now - timedelta(days=1), warn_days=30, critical_days=7)[0] == "expired"
    assert classify_cert_status(now + timedelta(days=3), warn_days=30, critical_days=7)[0] == "critical"
    assert classify_cert_status(now + timedelta(days=15), warn_days=30, critical_days=7)[0] == "warn"
    assert classify_cert_status(now + timedelta(days=120), warn_days=30, critical_days=7)[0] == "ok"


def test_extract_lb_fields_https_auto_cert() -> None:
    item = {
        "name": "www-lb",
        "namespace": "j-granieri",
        "get_spec": {
            "domains": ["www.example.com"],
            "https_auto_cert": {"http_redirect": True},
            "advertise_on_public_default_vip": {},
            "app_firewall": {"name": "waf"},
            "bot_defense": {"policy": {}},
            "default_route_pools": [{"pool": {"name": "www-pool"}}],
        },
    }
    out = extract_lb_fields(item)
    assert out["lb_type"] == "https"
    assert out["advertise_mode"] == "advertise_on_public_default_vip"
    assert out["has_waf"] is True
    assert out["has_bot_defense"] is True
    assert out["origin_pool_refs"] == ["www-pool"]


def test_extract_lb_fields_http_legacy() -> None:
    item = {
        "name": "legacy",
        "namespace": "j-granieri",
        "get_spec": {
            "domains": ["internal.example.local"],
            "http": {"port": 80},
            "advertise_custom": {"advertise_where": []},
            "default_route_pools": [{"pool": {"name": "legacy-pool"}}],
        },
    }
    out = extract_lb_fields(item)
    assert out["lb_type"] == "http"
    assert out["advertise_mode"] == "advertise_custom"
    assert out["has_waf"] is False


def test_extract_cert_fields_auto_cert() -> None:
    spec = {
        "auto_cert_info": {
            "auto_cert_expiry": "2026-12-31T00:00:00Z",
            "auto_cert_subject_name": "CN=foo.example.com",
        }
    }
    out = extract_cert_fields(spec)
    assert out["auto_cert"] is True
    assert out["not_after"] is not None
    assert out["not_after"].year == 2026


def test_extract_cert_fields_pem_from_string_url() -> None:
    # Minimal self-signed for the test
    import base64

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subj = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "unit.example")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subj)
        .issuer_name(subj)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("unit.example")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    b64 = base64.b64encode(pem.encode()).decode()
    spec = {"certificate_url": f"string:///{b64}"}
    out = extract_cert_fields(spec)
    assert out["subject"] == "unit.example"
    assert out["san_dns"] == ["unit.example"]
    assert out["not_after"] is not None


def test_extract_pool_fields() -> None:
    item = {
        "name": "p1",
        "namespace": "j-granieri",
        "get_spec": {
            "origin_servers": [{"public_ip": {"ip": "1.2.3.4"}}, {"public_ip": {"ip": "5.6.7.8"}}],
            "port": 8443,
            "loadbalancer_algorithm": "ROUND_ROBIN",
            "healthcheck": [{"name": "hc1"}],
        },
    }
    out = extract_pool_fields(item)
    assert out["origin_count"] == 2
    assert out["port"] == 8443
    assert out["healthcheck_refs"] == ["hc1"]
