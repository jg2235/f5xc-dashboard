"""HTTP API routers."""
from fastapi import APIRouter

from app.api import (
    alerts,
    analytics,
    analytics_api,
    analytics_bot,
    analytics_security,
    auth,
    certificates,
    health,
    loadbalancers,
    policies,
    pools,
    sync,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(loadbalancers.router, prefix="/loadbalancers", tags=["load-balancers"])
api_router.include_router(certificates.router, prefix="/certificates", tags=["certificates"])
api_router.include_router(pools.router, prefix="/pools", tags=["origin-pools"])
api_router.include_router(policies.router, prefix="/policies", tags=["policies"])
api_router.include_router(analytics.router, prefix="/analytics/waf", tags=["analytics-waf"])
api_router.include_router(analytics_bot.router, prefix="/analytics/bot", tags=["analytics-bot"])
api_router.include_router(analytics_api.router, prefix="/analytics/api", tags=["analytics-api"])
api_router.include_router(
    analytics_security.router, prefix="/analytics/security", tags=["analytics-security"],
)
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
