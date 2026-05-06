"""Seed initial tenant + admin user, then run an initial sync."""
from __future__ import annotations

import os
import sys

from sqlalchemy import select

from app.auth.security import hash_password
from app.config import get_settings
from app.db import SessionLocal, engine
from app.logging_config import configure_logging, get_logger
from app.migrations import run_migrations
from app.models import Tenant, User

configure_logging()
log = get_logger("seed")


def main() -> None:
    settings = get_settings()
    # Ensure schema is at head before doing anything (idempotent).
    run_migrations(engine)

    admin_user = os.environ.get("SEED_ADMIN_USERNAME", "admin")
    admin_pass = os.environ.get("SEED_ADMIN_PASSWORD", "changeme")

    with SessionLocal() as db:
        tenant = db.execute(select(Tenant).where(Tenant.name == "default")).scalar_one_or_none()
        if tenant is None:
            # v0.9.0 — populate `namespaces` array directly. Single-element
            # list mirrors the F5XC_NAMESPACE env var (kept singular for
            # backward compat). Operators add additional namespaces post-seed
            # via `make namespace-add NAMESPACE=foo`.
            tenant = Tenant(
                name="default",
                f5xc_tenant=settings.f5xc_tenant,
                f5xc_namespace=settings.f5xc_namespace,
                namespaces=[settings.f5xc_namespace],
                f5xc_api_token=settings.f5xc_api_token,
            )
            db.add(tenant)
            db.flush()
            log.info("tenant_created", name=tenant.name, f5xc_tenant=tenant.f5xc_tenant)
        else:
            # v0.9.0 — idempotent populate: if `namespaces` is NULL on an
            # existing row (came from a pre-v0.9.0 install), populate from
            # the legacy column. Migration 0011 already does this for the
            # default tenant, but seed re-runs should also be safe.
            if not tenant.namespaces and tenant.f5xc_namespace:
                tenant.namespaces = [tenant.f5xc_namespace]
                log.info(
                    "tenant_namespaces_populated",
                    name=tenant.name, namespaces=tenant.namespaces,
                )
            else:
                log.info("tenant_exists", name=tenant.name)

        user = db.execute(select(User).where(User.username == admin_user)).scalar_one_or_none()
        if user is None:
            user = User(
                tenant_id=tenant.id,
                username=admin_user,
                email=None,
                hashed_password=hash_password(admin_pass),
                role="admin",
                is_active=True,
            )
            db.add(user)
            log.info("admin_created", username=admin_user)
        else:
            log.info("admin_exists", username=admin_user)

        db.commit()

    # Run all syncs in dependency-correct order
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

    lb = sync_loadbalancers.apply().result
    certs = sync_certificates.apply().result
    pools = sync_origin_pools.apply().result
    sites = sync_sites.apply().result
    pols = sync_policies.apply().result   # Must be before api_endpoints (declared_endpoints)
    hc = sync_healthchecks.apply().result
    wm = sync_waf_metrics.apply().result
    we = sync_waf_events.apply().result
    bm = sync_bot_metrics.apply().result
    be = sync_bot_events.apply().result
    ads = sync_api_discovery_state.apply().result
    aep = sync_api_endpoints.apply().result
    am = sync_api_metrics.apply().result
    # Slice 7: must run AFTER event feeds — correlator + alert rules read those tables
    ap = refresh_attacker_profiles.apply().result
    al = evaluate_alert_rules.apply().result

    log.info(
        "initial_sync_complete",
        lb=lb, certs=certs, pools=pools, sites=sites,
        policies=pols, healthchecks=hc,
        waf_metrics=wm, waf_events=we,
        bot_metrics=bm, bot_events=be,
        api_discovery=ads, api_endpoints=aep, api_metrics=am,
        attacker_profiles=ap, alerts=al,
    )
    print("Seed complete.")
    print(f"  Username: {admin_user}")
    print(f"  Password: {admin_pass}")
    print(f"  Initial sync: lb={lb}, certs={certs}, pools={pools}, "
          f"sites={sites}, policies={pols}, hc={hc}")
    print(f"  Analytics: waf_metrics={wm}, waf_events={we}, "
          f"bot_metrics={bm}, bot_events={be}")
    print(f"  API: discovery={ads}, endpoints={aep}, metrics={am}")
    print(f"  Security: attackers={ap}, alerts={al}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("seed_failed")
        sys.exit(1)
