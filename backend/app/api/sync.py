"""Manual sync triggers (admin only)."""
from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.auth.dependencies import require_admin
from app.models import User
from app.workers.tasks.evaluate_alert_rules import evaluate_alert_rules
from app.workers.tasks.refresh_attacker_profiles import refresh_attacker_profiles
from app.workers.tasks.sync_api_discovery_state import sync_api_discovery_state
from app.workers.tasks.sync_api_endpoints import sync_api_endpoints
from app.workers.tasks.sync_api_metrics import sync_api_metrics
from app.workers.tasks.sync_bot_events import sync_bot_events
from app.workers.tasks.sync_bot_metrics import sync_bot_metrics
from app.workers.tasks.sync_certificates import sync_certificates
from app.workers.tasks.sync_healthcheck_configs import sync_healthcheck_configs
from app.workers.tasks.sync_healthchecks import sync_healthchecks
from app.workers.tasks.sync_loadbalancers import sync_loadbalancers
from app.workers.tasks.sync_origin_pools import sync_origin_pools
from app.workers.tasks.sync_policies import sync_policies
from app.workers.tasks.sync_pool_re_health import sync_pool_re_health
from app.workers.tasks.sync_sites import sync_sites
from app.workers.tasks.sync_waf_events import sync_waf_events
from app.workers.tasks.sync_waf_metrics import sync_waf_metrics

router = APIRouter()


@router.post("/loadbalancers", summary="Trigger LB sync")
def trigger_lb_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_loadbalancers.apply().result}


@router.post("/certificates", summary="Trigger certificate sync")
def trigger_cert_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_certificates.apply().result}


@router.post("/origin-pools", summary="Trigger origin pool sync")
def trigger_pool_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_origin_pools.apply().result}


@router.post("/sites", summary="Trigger site sync")
def trigger_site_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_sites.apply().result}


@router.post("/policies", summary="Trigger policy sync")
def trigger_policy_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_policies.apply().result}


@router.post("/healthchecks", summary="Trigger healthcheck sync")
def trigger_healthcheck_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_healthchecks.apply().result}


@router.post("/healthcheck-configs", summary="Trigger healthcheck config sync")
def trigger_healthcheck_config_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_healthcheck_configs.apply().result}


@router.post("/pool-re-health", summary="Trigger pool RE health sync")
def trigger_pool_re_health_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_pool_re_health.apply().result}


@router.post("/waf-events", summary="Trigger WAF events sync")
def trigger_waf_events_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_waf_events.apply().result}


@router.post("/waf-metrics", summary="Trigger WAF metrics sync")
def trigger_waf_metrics_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_waf_metrics.apply().result}


@router.post("/bot-events", summary="Trigger bot events sync")
def trigger_bot_events_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_bot_events.apply().result}


@router.post("/bot-metrics", summary="Trigger bot metrics sync")
def trigger_bot_metrics_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_bot_metrics.apply().result}


@router.post("/api-endpoints", summary="Trigger API endpoint discovery sync")
def trigger_api_endpoints_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_api_endpoints.apply().result}


@router.post("/api-discovery-state", summary="Trigger API discovery state sync")
def trigger_api_discovery_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_api_discovery_state.apply().result}


@router.post("/api-metrics", summary="Trigger per-endpoint API metrics sync")
def trigger_api_metrics_sync(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": sync_api_metrics.apply().result}


@router.post("/attacker-profiles", summary="Refresh attacker profiles cache (slice 7)")
def trigger_attacker_profiles(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": refresh_attacker_profiles.apply().result}


@router.post("/alerts/evaluate", summary="Evaluate alert rules now (slice 7)")
def trigger_alerts_evaluate(_: User = Depends(require_admin)) -> dict:
    return {"status": "ok", "result": evaluate_alert_rules.apply().result}


# Ordered (key, human label, Celery task) tuples. Order matters: dependency
# stages first (LBs/pools/sites), then policies, then metric/event feeds, then
# slice-7 derivations that read those feeds. Shared by the blocking /all
# endpoint and the streaming /all/stream endpoint so they never drift.
_SYNC_STEPS = [
    ("load_balancers", "Load balancers", sync_loadbalancers),
    ("certificates", "Certificates", sync_certificates),
    ("origin_pools", "Origin pools", sync_origin_pools),
    ("healthcheck_configs", "Health check configs", sync_healthcheck_configs),
    ("sites", "Sites", sync_sites),
    ("policies", "Policies", sync_policies),
    ("healthchecks", "Health checks", sync_healthchecks),
    ("waf_metrics", "WAF metrics", sync_waf_metrics),
    ("waf_events", "WAF events", sync_waf_events),
    ("bot_metrics", "Bot metrics", sync_bot_metrics),
    ("bot_events", "Bot events", sync_bot_events),
    ("api_discovery_state", "API discovery state", sync_api_discovery_state),
    ("api_endpoints", "API endpoints", sync_api_endpoints),
    ("api_metrics", "API metrics", sync_api_metrics),
    # Slice 7: must run after the events feeds
    ("attacker_profiles", "Attacker profiles", refresh_attacker_profiles),
    ("alerts", "Alerts", evaluate_alert_rules),
]


@router.post("/all", summary="Trigger all syncs (correct dependency order)")
def trigger_all(_: User = Depends(require_admin)) -> dict:
    return {key: task.apply().result for key, _label, task in _SYNC_STEPS}


def _sse(obj: dict) -> str:
    """Encode one Server-Sent Events message."""
    return f"data: {json.dumps(obj)}\n\n"


@router.get("/all/stream", summary="Trigger all syncs with per-step SSE progress")
def trigger_all_stream(_: User = Depends(require_admin)) -> StreamingResponse:
    """Run every sync step in order, streaming progress as Server-Sent Events.

    Emits, in order:
      {"type": "start", "total": N}
      {"type": "step",     "index": i, "total": N, "key", "label"}   # before each
      {"type": "progress", "index": i+1, "total": N, "key", "label",
                           "status": "ok"|"error", "error": str|None} # after each
      {"type": "done", "total": N}

    GET (not POST) so the browser's EventSource can consume it; auth still
    flows via the session cookie and GET is CSRF-exempt.
    """
    steps = _SYNC_STEPS
    total = len(steps)

    def gen() -> Iterator[str]:
        yield _sse({"type": "start", "total": total})
        for i, (key, label, task) in enumerate(steps):
            yield _sse({"type": "step", "index": i, "total": total, "key": key, "label": label})
            result = task.apply()
            ok = result.successful()
            yield _sse({
                "type": "progress",
                "index": i + 1,
                "total": total,
                "key": key,
                "label": label,
                "status": "ok" if ok else "error",
                "error": None if ok else str(result.result),
            })
        yield _sse({"type": "done", "total": total})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Disable proxy buffering so events flush immediately.
            "X-Accel-Buffering": "no",
        },
    )
