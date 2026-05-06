"""F5 XC REST API client.

Wraps the f5xc-api skill patterns:
- httpx.Client with session reuse
- Retries on 429/5xx with exponential backoff
- Mock mode loads fixture JSON
- Logs every call at DEBUG, errors at WARNING+
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings, get_settings
from app.logging_config import get_logger

log = get_logger(__name__)


class F5XCError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class F5XCClient:
    """Thin wrapper around the F5 XC REST API."""

    FIXTURES_DIR = Path(__file__).parent / "fixtures"

    POLICY_URL_SEGMENT = {
        "app_firewall": "app_firewalls",
        "service_policy": "service_policys",
        "bot_defense_policy": "bot_defense_policys",
        "api_definition": "api_definitions",
    }

    def __init__(
        self,
        *,
        tenant: str,
        api_token: str,
        namespace: str,
        mock: bool = False,
        timeout: float = 30.0,
        max_retries: int = 5,
        api_url_template: str = "https://{tenant}.console.ves.io",
    ) -> None:
        self.tenant = tenant
        self.namespace = namespace
        self.mock = mock
        self.max_retries = max_retries
        self.base_url = api_url_template.format(tenant=tenant)

        self._client: httpx.Client | None = None
        if not mock:
            if not api_token:
                raise ValueError("F5XC_API_TOKEN is required when F5XC_MOCK=false")
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={
                    "Authorization": f"APIToken {api_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "f5xc-dashboard/0.4",
                },
                timeout=timeout,
            )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def __enter__(self) -> F5XCClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if self.mock:
            return self._mock_request(method, path, params=kwargs.get("params"), json_body=kwargs.get("json"))
        return self._live_request(method, path, **kwargs)

    def _live_request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        assert self._client is not None

        def _is_retryable(exc: BaseException) -> bool:
            """Retry only transport errors and transient HTTP failures (429, 5xx).
            4xx errors (404 NotFound, 403 Forbidden, 400 BadRequest, etc.) are
            terminal — retrying them just wastes 15+ seconds per call.
            """
            if isinstance(exc, httpx.TransportError):
                return True
            if isinstance(exc, F5XCError):
                code = exc.status_code or 0
                return code == 429 or code >= 500
            return False

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            retry=retry_if_exception(_is_retryable),
            before_sleep=before_sleep_log(log, 30),  # type: ignore[arg-type]
        )
        def _do() -> dict[str, Any]:
            resp = self._client.request(method, path, **kwargs)  # type: ignore[union-attr]
            if resp.status_code == 429 or resp.status_code >= 500:
                raise F5XCError(
                    f"Retryable status {resp.status_code} on {method} {path}",
                    status_code=resp.status_code,
                    body=resp.text[:500],
                )
            if resp.status_code >= 400:
                log.warning(
                    "f5xc_client_error",
                    method=method, path=path,
                    status=resp.status_code, body=resp.text[:500],
                )
                raise F5XCError(
                    f"{resp.status_code} on {method} {path}: {resp.text[:200]}",
                    status_code=resp.status_code, body=resp.text,
                )
            return resp.json() if resp.content else {}

        log.debug("f5xc_request", method=method, path=path, mock=False)
        return _do()

    def _mock_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        log.debug("f5xc_request", method=method, path=path, mock=True)
        if method.upper() not in ("GET", "POST"):
            return {"mock_write_noop": True, "method": method, "path": path}

        sanitized = path.strip("/").split("?")[0].replace("/", "__")
        candidates = [self.FIXTURES_DIR / f"{sanitized}.json"]

        clean_path = path.split("?")[0].rstrip("/")

        # Slice 1/2 patterns
        if clean_path.endswith("http_loadbalancers"):
            candidates.append(self.FIXTURES_DIR / "http_loadbalancers_list.json")
        elif clean_path.endswith("certificate_chains"):
            candidates.append(self.FIXTURES_DIR / "certificate_chains_list.json")
        elif clean_path.endswith("origin_pools"):
            candidates.append(self.FIXTURES_DIR / "origin_pools_list.json")
        elif clean_path.endswith("/sites"):
            candidates.append(self.FIXTURES_DIR / "sites_list.json")
        elif "/origin_servers/health" in clean_path:
            parts = clean_path.split("/")
            try:
                pool_idx = parts.index("origin_pools") + 1
                pool = parts[pool_idx]
            except (ValueError, IndexError):
                pool = "unknown"
            site = (params or {}).get("site", "unknown")
            candidates.append(self.FIXTURES_DIR / f"origin_health__{pool}__{site}.json")
            candidates.append(self.FIXTURES_DIR / f"origin_health__{pool}.json")
            candidates.append(self.FIXTURES_DIR / "origin_health_default.json")
        else:
            # Detail GET routing — list responses on the live API return
            # metadata only (get_spec=null); detail GET is required to hydrate
            # the spec. The mock derives detail responses from the existing
            # `*_list.json` fixtures by looking up the item by name.
            detail = self._mock_detail_lookup(clean_path)
            if detail is not None:
                return detail

        # Slice 3 patterns
        for url_segment in self.POLICY_URL_SEGMENT.values():
            if clean_path.endswith(f"/{url_segment}"):
                ns = self._extract_namespace(clean_path)
                if ns:
                    candidates.append(self.FIXTURES_DIR / f"{ns}_{url_segment}.json")
                candidates.append(self.FIXTURES_DIR / f"{url_segment}_default.json")

        # Slice 4 patterns
        if clean_path.endswith("/app/security_events"):
            # POST with body filter: { lb_name, namespace, ... }
            body = json_body or {}
            lb = body.get("lb_name") or "all"
            candidates.append(self.FIXTURES_DIR / f"security_events__{lb}.json")
            candidates.append(self.FIXTURES_DIR / "security_events_default.json")
        elif "/metrics/multi_v2" in clean_path:
            body = json_body or {}
            lb = body.get("lb_name") or "all"
            # Slice 6 — API per-endpoint metrics also use this URL but with
            # group_by=["method","endpoint"]. Route to api_metrics fixtures.
            if body.get("group_by"):
                candidates.append(self.FIXTURES_DIR / f"api_metrics__{lb}.json")
                candidates.append(self.FIXTURES_DIR / "api_metrics_default.json")
            else:
                candidates.append(self.FIXTURES_DIR / f"metrics_multi__{lb}.json")
                candidates.append(self.FIXTURES_DIR / "metrics_multi_default.json")
        elif clean_path.endswith("/app/bot_traffic"):
            body = json_body or {}
            lb = body.get("lb_name") or "all"
            candidates.append(self.FIXTURES_DIR / f"bot_traffic__{lb}.json")
            candidates.append(self.FIXTURES_DIR / "bot_traffic_default.json")
        elif clean_path.endswith("/api_endpoints"):
            # Slice 6 — per-LB discovered endpoints inventory
            # /api/data/namespaces/{ns}/http_loadbalancers/{lb}/api_endpoints
            parts = clean_path.split("/")
            try:
                lb_idx = parts.index("http_loadbalancers") + 1
                lb = parts[lb_idx]
            except (ValueError, IndexError):
                lb = "default"
            candidates.append(self.FIXTURES_DIR / f"api_endpoints__{lb}.json")
            candidates.append(self.FIXTURES_DIR / "api_endpoints_default.json")
        elif clean_path.endswith("/api_discovery_state"):
            # /api/data/namespaces/{ns}/http_loadbalancers/{lb}/api_discovery_state
            parts = clean_path.split("/")
            try:
                lb_idx = parts.index("http_loadbalancers") + 1
                lb = parts[lb_idx]
            except (ValueError, IndexError):
                lb = "default"
            candidates.append(self.FIXTURES_DIR / f"api_discovery_state__{lb}.json")
            candidates.append(self.FIXTURES_DIR / "api_discovery_state_default.json")

        for fixture in candidates:
            if fixture.exists():
                return json.loads(fixture.read_text())

        log.warning("f5xc_mock_fixture_missing", path=path, params=params, tried=[str(c) for c in candidates])
        return {"items": []} if "events" in clean_path else {"data": []}

    @staticmethod
    def _extract_namespace(path: str) -> str | None:
        parts = path.strip("/").split("/")
        try:
            ns_idx = parts.index("namespaces") + 1
            return parts[ns_idx]
        except (ValueError, IndexError):
            return None

    # Map of `/segment/name` patterns to list fixture filenames.
    _DETAIL_ROUTES = {
        "http_loadbalancers": "http_loadbalancers_list.json",
        "certificate_chains": "certificate_chains_list.json",
        "origin_pools": "origin_pools_list.json",
        "app_firewalls": "{ns}_app_firewalls.json",
        "service_policys": "{ns}_service_policys.json",
        "bot_defense_policys": "{ns}_bot_defense_policys.json",
        "api_definitions": "{ns}_api_definitions.json",
    }

    def _mock_detail_lookup(self, clean_path: str) -> dict[str, Any] | None:
        """Synthesize a detail GET response from the corresponding list fixture.

        F5 XC list responses return metadata only (get_spec=null); the live
        client now calls per-item detail GETs to hydrate spec. To keep the
        mock consistent with this contract, look up the item by name in the
        list fixture and return it wrapped as a detail response (with `spec`
        as a top-level field, matching live shape).
        """
        parts = clean_path.strip("/").split("/")
        # Find segment + name pair: parts[-2] = segment, parts[-1] = name
        if len(parts) < 2:
            return None
        segment, name = parts[-2], parts[-1]
        fixture_template = self._DETAIL_ROUTES.get(segment)
        if fixture_template is None:
            return None
        ns = self._extract_namespace(clean_path) or "default"
        fixture_path = self.FIXTURES_DIR / fixture_template.format(ns=ns)
        if not fixture_path.exists():
            # Try the default-suffix policy fixture (slice 3 fallback)
            policy_segment_default = self.FIXTURES_DIR / f"{segment}_default.json"
            if policy_segment_default.exists():
                fixture_path = policy_segment_default
            else:
                return None
        try:
            data = json.loads(fixture_path.read_text())
        except json.JSONDecodeError:
            return None
        items = data.get("items") or []
        for item in items:
            if item.get("name") == name:
                spec = item.get("get_spec") or item.get("spec") or {}
                return {
                    "metadata": {
                        "name": item.get("name"),
                        "namespace": item.get("namespace"),
                        "labels": item.get("labels", {}),
                        "annotations": item.get("annotations", {}),
                        "description": item.get("description", ""),
                    },
                    "system_metadata": item.get("system_metadata"),
                    "spec": spec,
                }
        return None

    # ------------------------------------------------------------------
    # Config-plane (slice 1)
    # ------------------------------------------------------------------
    def list_http_load_balancers(self, namespace: str | None = None) -> list[dict[str, Any]]:
        ns = namespace or self.namespace
        return self._request("GET", f"/api/config/namespaces/{ns}/http_loadbalancers").get("items", [])

    def get_http_load_balancer(self, name: str, namespace: str | None = None) -> dict[str, Any]:
        ns = namespace or self.namespace
        return self._request(
            "GET",
            f"/api/config/namespaces/{ns}/http_loadbalancers/{name}",
        )

    def list_certificate_chains(self, namespace: str | None = None) -> list[dict[str, Any]]:
        ns = namespace or self.namespace
        return self._request("GET", f"/api/config/namespaces/{ns}/certificate_chains").get("items", [])

    def get_certificate_chain(self, name: str, namespace: str | None = None) -> dict[str, Any]:
        ns = namespace or self.namespace
        return self._request(
            "GET",
            f"/api/config/namespaces/{ns}/certificate_chains/{name}",
        )

    def list_origin_pools(self, namespace: str | None = None) -> list[dict[str, Any]]:
        ns = namespace or self.namespace
        return self._request("GET", f"/api/config/namespaces/{ns}/origin_pools").get("items", [])

    def get_origin_pool(self, name: str, namespace: str | None = None) -> dict[str, Any]:
        ns = namespace or self.namespace
        return self._request(
            "GET",
            f"/api/config/namespaces/{ns}/origin_pools/{name}",
        )

    # ------------------------------------------------------------------
    # Sites + health (slice 2)
    # ------------------------------------------------------------------
    def list_sites(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/config/namespaces/system/sites").get("items", [])

    def get_namespace_metadata(self, name: str) -> dict[str, Any]:
        """GET F5 XC namespace metadata. Raises F5XCError on 404 (namespace
        does not exist) or 4xx/5xx (RBAC, etc.).

        Used for namespace existence validation (probe-on-add). Unlike list-
        style endpoints (/api/config/namespaces/{ns}/<resource>), which return
        200+empty for non-existent namespaces, this hits the namespace
        registry and is strict about existence.

        Endpoint: GET /api/web/namespaces/{name}
        """
        return self._request("GET", f"/api/web/namespaces/{name}")

    def get_site(self, name: str) -> dict[str, Any] | None:
        """GET a single site detail. Returns None on 404 (token lacks scope).

        F5 XC restricts per-site detail GET on the system namespace for many
        tokens — typically RE sites are restricted, CE sites are not. Caller
        should handle None by falling back to name-based classification.
        """
        try:
            return self._request("GET", f"/api/config/namespaces/system/sites/{name}")
        except F5XCError as e:
            if e.status_code == 404:
                return None
            raise

    def get_origin_health(
        self, pool_name: str, site_name: str, namespace: str | None = None,
    ) -> dict[str, Any]:
        ns = namespace or self.namespace
        return self._request(
            "GET",
            f"/api/data/namespaces/{ns}/origin_pools/{pool_name}/origin_servers/health",
            params={"site": site_name},
        )

    # ------------------------------------------------------------------
    # Policies (slice 3)
    # ------------------------------------------------------------------
    def list_policies(self, policy_type: str, namespace: str) -> list[dict[str, Any]]:
        segment = self.POLICY_URL_SEGMENT.get(policy_type)
        if segment is None:
            raise ValueError(f"Unknown policy_type: {policy_type}")
        return self._request(
            "GET", f"/api/config/namespaces/{namespace}/{segment}",
        ).get("items", [])

    def get_policy(self, policy_type: str, name: str, namespace: str) -> dict[str, Any]:
        segment = self.POLICY_URL_SEGMENT.get(policy_type)
        if segment is None:
            raise ValueError(f"Unknown policy_type: {policy_type}")
        return self._request(
            "GET",
            f"/api/config/namespaces/{namespace}/{segment}/{name}",
        )

    # ------------------------------------------------------------------
    # WAF analytics (slice 4)
    # ------------------------------------------------------------------
    def get_security_events(
        self,
        lb_name: str,
        *,
        start_time: str,
        end_time: str,
        max_events: int = 1000,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/data/namespaces/{ns}/app/security_events.

        F5 XC uses a JSON body on POST for time-windowed event queries.
        Returns `{"events": [...]}`.
        """
        ns = namespace or self.namespace
        body = {
            "namespace": ns,
            "lb_name": lb_name,
            "start_time": start_time,
            "end_time": end_time,
            "limit": max_events,
        }
        return self._request(
            "POST",
            f"/api/data/namespaces/{ns}/app/security_events",
            json=body,
        )

    def get_metrics(
        self,
        lb_name: str,
        *,
        start_time: str,
        end_time: str,
        step: str = "60s",
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/data/namespaces/{ns}/metrics/multi_v2.

        Returns time-series for request_count / blocked_count / monitored_count /
        error_count, bucketed at `step`.
        """
        ns = namespace or self.namespace
        body = {
            "namespace": ns,
            "lb_name": lb_name,
            "start_time": start_time,
            "end_time": end_time,
            "step": step,
            "metric_names": [
                "loadbalancer.request_count",
                "loadbalancer.waf_blocked_count",
                "loadbalancer.waf_monitored_count",
                "loadbalancer.error_count",
            ],
        }
        return self._request(
            "POST",
            f"/api/data/namespaces/{ns}/metrics/multi_v2",
            json=body,
        )

    # ------------------------------------------------------------------
    # Bot analytics (slice 5)
    # ------------------------------------------------------------------
    def get_bot_traffic(
        self,
        lb_name: str,
        *,
        start_time: str,
        end_time: str,
        max_events: int = 1000,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/data/namespaces/{ns}/app/bot_traffic.

        Bot Defense Advanced (BD-A) telemetry endpoint. Returns rich per-event
        bot decision data — challenge result, confidence score, device anomalies,
        bot category. Standard BD events come through get_security_events() instead.
        """
        ns = namespace or self.namespace
        body = {
            "namespace": ns,
            "lb_name": lb_name,
            "start_time": start_time,
            "end_time": end_time,
            "limit": max_events,
        }
        return self._request(
            "POST",
            f"/api/data/namespaces/{ns}/app/bot_traffic",
            json=body,
        )

    # ------------------------------------------------------------------
    # API discovery + per-endpoint metrics (slice 6)
    # ------------------------------------------------------------------
    def list_api_endpoints(
        self, lb_name: str, *, namespace: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET discovered endpoints for an LB.

        F5 XC's discovery surface returns a flat list of unique endpoints
        with method, path, sample counts, inferred shape, auth observation.
        """
        ns = namespace or self.namespace
        return self._request(
            "GET",
            f"/api/data/namespaces/{ns}/http_loadbalancers/{lb_name}/api_endpoints",
        ).get("items", [])

    def get_api_discovery_state(
        self, lb_name: str, *, namespace: str | None = None,
    ) -> dict[str, Any]:
        """GET ML discovery lifecycle state for an LB.

        Returns shape:
          {
            "state": "learning" | "mature" | "enforcing" | "disabled",
            "confidence_score": int,
            "total_endpoints_discovered": int,
            "total_traffic_samples": int,
            "last_learning_update": "<iso>",
            "state_changed_at": "<iso>"
          }
        """
        ns = namespace or self.namespace
        return self._request(
            "GET",
            f"/api/data/namespaces/{ns}/http_loadbalancers/{lb_name}/api_discovery_state",
        )

    def get_api_endpoint_metrics(
        self,
        lb_name: str,
        *,
        start_time: str,
        end_time: str,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """POST per-endpoint metrics (req count + 4xx/5xx + p50/p95/p99 latency).

        F5 XC's metrics_multi_v2 with method+endpoint dimension grouping.
        """
        ns = namespace or self.namespace
        body = {
            "namespace": ns,
            "lb_name": lb_name,
            "start_time": start_time,
            "end_time": end_time,
            "step": "60s",
            "group_by": ["method", "endpoint"],
            "metric_names": [
                "loadbalancer.request_count",
                "loadbalancer.http_4xx_count",
                "loadbalancer.http_5xx_count",
                "loadbalancer.latency_p50",
                "loadbalancer.latency_p95",
                "loadbalancer.latency_p99",
            ],
        }
        return self._request(
            "POST",
            f"/api/data/namespaces/{ns}/metrics/multi_v2",
            json=body,
        )


def get_f5xc_client(settings: Settings | None = None) -> F5XCClient:
    s = settings or get_settings()
    return F5XCClient(
        tenant=s.f5xc_tenant,
        api_token=s.f5xc_api_token,
        namespace=s.f5xc_namespace,
        mock=s.f5xc_mock,
        timeout=s.f5xc_request_timeout_seconds,
        max_retries=s.f5xc_max_retries,
        api_url_template=s.f5xc_api_url_template,
    )
