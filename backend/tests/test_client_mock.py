"""F5XCClient mock-mode tests — load fixture JSON."""
from __future__ import annotations

from app.f5xc.client import F5XCClient


def test_client_mock_lists_lbs() -> None:
    client = F5XCClient(
        tenant="f5-amer-ent",
        api_token="",
        namespace="j-granieri",
        mock=True,
    )
    lbs = client.list_http_load_balancers()
    assert len(lbs) >= 1
    names = {lb["name"] for lb in lbs}
    assert "www-prod-lb" in names
    assert "api-prod-lb" in names


def test_client_mock_lists_certs() -> None:
    client = F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)
    certs = client.list_certificate_chains()
    names = {c["name"] for c in certs}
    assert "api-example-com-2026" in names
    assert "legacy-expired-cert" in names


def test_client_mock_lists_pools() -> None:
    client = F5XCClient(tenant="f5-amer-ent", api_token="", namespace="j-granieri", mock=True)
    pools = client.list_origin_pools()
    assert len(pools) == 3


def test_client_default_url_template() -> None:
    """Default URL template uses console.ves.io."""
    client = F5XCClient(tenant="acme", api_token="", namespace="default", mock=True)
    assert client.base_url == "https://acme.console.ves.io"


def test_client_legacy_volterra_url_template() -> None:
    """Legacy ves.volterra.io URL template is supported."""
    client = F5XCClient(
        tenant="f5-amer-ent",
        api_token="",
        namespace="j-granieri",
        mock=True,
        api_url_template="https://{tenant}.ves.volterra.io",
    )
    assert client.base_url == "https://f5-amer-ent.ves.volterra.io"


def test_client_custom_url_template() -> None:
    """Arbitrary URL templates work — supports private/airgap deployments."""
    client = F5XCClient(
        tenant="prod",
        api_token="",
        namespace="default",
        mock=True,
        api_url_template="https://xc.internal.corp.example/{tenant}",
    )
    assert client.base_url == "https://xc.internal.corp.example/prod"
