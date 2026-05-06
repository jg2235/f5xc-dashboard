"""Manual sync triggers (admin only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

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
from app.workers.tasks.sync_healthchecks import sync_healthchecks
from app.workers.tasks.sync_loadbalancers import sync_loadbalancers
from app.workers.tasks.sync_origin_pools import sync_origin_pools
from app.workers.tasks.sync_policies import sync_policies
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


@router.post("/all", summary="Trigger all syncs (correct dependency order)")
def trigger_all(_: User = Depends(require_admin)) -> dict:
    return {
        "load_balancers": sync_loadbalancers.apply().result,
        "certificates": sync_certificates.apply().result,
        "origin_pools": sync_origin_pools.apply().result,
        "sites": sync_sites.apply().result,
        "policies": sync_policies.apply().result,
        "healthchecks": sync_healthchecks.apply().result,
        "waf_metrics": sync_waf_metrics.apply().result,
        "waf_events": sync_waf_events.apply().result,
        "bot_metrics": sync_bot_metrics.apply().result,
        "bot_events": sync_bot_events.apply().result,
        "api_discovery_state": sync_api_discovery_state.apply().result,
        "api_endpoints": sync_api_endpoints.apply().result,
        "api_metrics": sync_api_metrics.apply().result,
        # Slice 7: must run after the events feeds
        "attacker_profiles": refresh_attacker_profiles.apply().result,
        "alerts": evaluate_alert_rules.apply().result,
    }
