"""Sync policies (app_firewall, service_policy, bot_defense_policy, api_definition).

For each tenant:
  1. Fetch each policy type from `shared` AND tenant's user namespace.
  2. Transform → upsert into the corresponding policy table.
  3. Rebuild PolicyAttachment from already-synced LB raw_specs.

Step 3 is intentionally idempotent and fast: it walks the LBs in the DB, not
the F5 XC API, so this task can run cheaply alongside (or after) sync_loadbalancers.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.f5xc.client import F5XCClient
from app.f5xc.transformers import (
    extract_api_definition_fields,
    extract_app_firewall_fields,
    extract_bot_defense_policy_fields,
    extract_lb_policy_attachments,
    extract_service_policy_fields,
)
from app.logging_config import get_logger
from app.models import (
    ApiDefinition,
    AppFirewall,
    BotDefensePolicy,
    LoadBalancer,
    PolicyAttachment,
    ServicePolicy,
)
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)

# Map policy_type → (model class, transformer)
_POLICY_HANDLERS = {
    "app_firewall": (AppFirewall, extract_app_firewall_fields),
    "service_policy": (ServicePolicy, extract_service_policy_fields),
    "bot_defense_policy": (BotDefensePolicy, extract_bot_defense_policy_fields),
    "api_definition": (ApiDefinition, extract_api_definition_fields),
}


def _upsert_policy(db, model, tenant_id, fields: dict, sync_started_at: datetime) -> None:
    """Build an UPSERT statement that handles all the per-model columns."""
    values = {**fields, "tenant_id": tenant_id, "last_seen_at": sync_started_at}
    # Drop the namespace key from fields to avoid clobbering on conflict
    stmt = insert(model).values(**values)
    update_fields = {k: getattr(stmt.excluded, k) for k in fields if k not in ("namespace", "name")}
    update_fields["last_seen_at"] = stmt.excluded.last_seen_at
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "namespace", "name"],
        set_=update_fields,
    )
    db.execute(stmt)


def _materialize_inline_bot_defense_policies(db, tenant_id, sync_started_at: datetime) -> int:
    """Synthesize BotDefensePolicy rows from each LB's inline bot_defense.

    F5 XC's modern API does not expose `/bot_defense_policys` as a separate
    endpoint (returns 404). Instead, bot defense is configured inline on each
    HTTP load balancer as `bot_defense.policy.protected_app_endpoints[]`.
    Each protected endpoint has its own name and mitigation rule.

    To make these visible in the dashboard's Policies → Bot Defense view and
    enable LB→bot_defense_policy linkage via PolicyAttachment, materialize one
    BotDefensePolicy row per protected endpoint. Synthesized rows live in the
    LB's namespace, not `shared`, since they're scoped to that LB.
    """
    lbs = db.execute(
        select(LoadBalancer).where(LoadBalancer.tenant_id == tenant_id)
    ).scalars().all()
    inserted = 0
    for lb in lbs:
        spec = lb.raw_spec or {}
        bot = spec.get("bot_defense") or spec.get("bot_defense_advanced")
        if not isinstance(bot, dict):
            continue
        policy = bot.get("policy") if isinstance(bot.get("policy"), dict) else {}
        endpoints = policy.get("protected_app_endpoints") or []
        if not isinstance(endpoints, list):
            continue
        for ep in endpoints:
            if not isinstance(ep, dict):
                continue
            metadata = ep.get("metadata") or {}
            ep_name = metadata.get("name")
            if not ep_name:
                continue
            mitigation = ep.get("mitigation") or {}
            path = ep.get("path") or {}
            paths_list: list[str] = []
            for path_key in ("prefix", "exact", "regex"):
                v = path.get(path_key)
                if v:
                    paths_list.append(v)
            stmt = insert(BotDefensePolicy).values(
                tenant_id=tenant_id,
                namespace=lb.namespace,
                name=ep_name,
                is_shared=False,
                protected_endpoint_count=1,
                protected_paths=paths_list,
                has_javascript_challenge="javascript_challenge" in mitigation,
                has_captcha_challenge="captcha_challenge" in mitigation,
                has_redirect="redirect" in mitigation,
                has_block="block" in mitigation,
                raw_spec={
                    "synthesized_from": "bot_defense.policy.protected_app_endpoints",
                    "lb_name": lb.name,
                    "endpoint": ep,
                },
                last_seen_at=sync_started_at,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["tenant_id", "namespace", "name"],
                set_={
                    "protected_paths": stmt.excluded.protected_paths,
                    "has_javascript_challenge": stmt.excluded.has_javascript_challenge,
                    "has_captcha_challenge": stmt.excluded.has_captcha_challenge,
                    "has_redirect": stmt.excluded.has_redirect,
                    "has_block": stmt.excluded.has_block,
                    "raw_spec": stmt.excluded.raw_spec,
                    "last_seen_at": stmt.excluded.last_seen_at,
                },
            )
            db.execute(stmt)
            inserted += 1
    return inserted


def _rebuild_policy_attachments(db, tenant_id, sync_started_at: datetime) -> int:
    """Walk synced LBs and (re)populate PolicyAttachment rows for this tenant."""
    # Wipe and rebuild — simpler than diffing, and the table is small.
    db.execute(delete(PolicyAttachment).where(PolicyAttachment.tenant_id == tenant_id))

    lbs = db.execute(
        select(LoadBalancer).where(LoadBalancer.tenant_id == tenant_id)
    ).scalars().all()
    inserted = 0
    for lb in lbs:
        # raw_spec is stored as the LB's `get_spec`, so wrap it back in the item shape
        # that the transformer expects.
        attachments = extract_lb_policy_attachments(
            {"name": lb.name, "namespace": lb.namespace, "get_spec": lb.raw_spec}
        )
        seen: set[tuple[str, str, str]] = set()
        for att in attachments:
            key = (att["policy_type"], att["policy_namespace"], att["policy_name"])
            if key in seen:
                continue
            seen.add(key)
            stmt = insert(PolicyAttachment).values(
                tenant_id=tenant_id,
                policy_type=att["policy_type"],
                policy_namespace=att["policy_namespace"],
                policy_name=att["policy_name"],
                lb_id=lb.id,
                last_seen_at=sync_started_at,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["tenant_id", "policy_type", "policy_namespace", "policy_name", "lb_id"],
                set_={"last_seen_at": stmt.excluded.last_seen_at},
            )
            db.execute(stmt)
            inserted += 1
    return inserted


@celery_app.task(name="app.workers.tasks.sync_policies.sync_policies")
def sync_policies() -> dict:
    settings = get_settings()
    totals = {"app_firewall": 0, "service_policy": 0, "bot_defense_policy": 0, "api_definition": 0}
    attachments = 0

    with session_scope() as db:
        tenants = iter_tenants(db)
        if not tenants:
            return {"tenants": 0, "policies": totals, "attachments": 0}

        for tenant in tenants:
            sync_started_at = datetime.now(UTC)
            successful_lists = 0  # count of (policy_type, namespace) lists that succeeded
            # v0.9.0 — operator-configured namespace list (was hardcoded literal)
            namespaces = tenant.effective_namespaces
            with F5XCClient(
                tenant=tenant.f5xc_tenant,
                api_token=settings.f5xc_api_token or tenant.f5xc_api_token,
                namespace=tenant.f5xc_namespace,
                mock=settings.f5xc_mock,
                timeout=settings.f5xc_request_timeout_seconds,
                max_retries=settings.f5xc_max_retries,
                api_url_template=settings.f5xc_api_url_template,
            ) as client:
                for policy_type, (model, transformer) in _POLICY_HANDLERS.items():
                    for ns in namespaces:
                        try:
                            listed = client.list_policies(policy_type, ns)
                        except Exception as exc:  # noqa: BLE001
                            log.warning(
                                "policy_list_failed",
                                policy_type=policy_type, namespace=ns, error=str(exc),
                            )
                            continue
                        successful_lists += 1
                        for stub in listed:
                            name = stub.get("name", "")
                            policy_ns = stub.get("namespace") or ns
                            if not name:
                                continue
                            # F5 XC auto-generates shadow service_policies as
                            # side-effects of inline bot defense configuration
                            # (one for js-insertion, one for protected-endpoints
                            # per LB). They appear in the API list but the F5
                            # console hides them from operators because they're
                            # implementation details, not user-managed policies.
                            # We filter them out at sync time. Note: only the
                            # 'shape-' prefix is system-generated. Other
                            # 'ves-io-' prefixed names (rate-limiter-policy,
                            # waf-exclusion) ARE user policies created via
                            # F5 XC's Manager UI flows — keep those.
                            if name.startswith("ves-io-http-loadbalancer-shape-"):
                                continue
                            # Per-policy detail GET — list returns metadata only.
                            try:
                                detail = client.get_policy(policy_type, name, policy_ns)
                            except Exception as exc:  # noqa: BLE001
                                log.warning(
                                    "policy_detail_fetch_failed",
                                    policy_type=policy_type,
                                    name=name, namespace=policy_ns, error=str(exc),
                                )
                                continue
                            item = {
                                **stub,
                                "spec": detail.get("spec") or detail.get("get_spec") or {},
                            }
                            fields = transformer(item)
                            if not fields["name"]:
                                continue
                            _upsert_policy(db, model, tenant.id, fields, sync_started_at)
                            totals[policy_type] += 1

            # Materialize inline bot defense from each LB as synthetic
            # BotDefensePolicy rows. F5 XC's modern API has no
            # /bot_defense_policys endpoint; bot config lives on the LB itself
            # under bot_defense.policy.protected_app_endpoints[].
            synthetic_bd = _materialize_inline_bot_defense_policies(db, tenant.id, sync_started_at)
            totals["bot_defense_policy"] += synthetic_bd

            attachments += _rebuild_policy_attachments(db, tenant.id, sync_started_at)

            # v0.8.0 — stale-row reaping for each policy table. Reap by
            # (tenant_id, last_seen_at < sync_started_at). Scoped to tenant
            # only because policies span shared + user namespace and synthetic
            # bot defense rows in the LB's namespace; one tenant-wide predicate
            # covers all three sources cleanly.
            #
            # Guard: if every list_policies call threw, treat as failure and
            # reap nothing.
            reaped = {"app_firewall": 0, "service_policy": 0, "bot_defense_policy": 0, "api_definition": 0}
            if successful_lists > 0:
                for policy_type, (model, _) in _POLICY_HANDLERS.items():
                    n = db.execute(
                        delete(model).where(
                            model.tenant_id == tenant.id,
                            model.last_seen_at < sync_started_at,
                        )
                    ).rowcount or 0
                    reaped[policy_type] = n
                if any(reaped.values()):
                    log.info(
                        "sync_policies_reaped_stale",
                        tenant=tenant.name,
                        reaped=reaped,
                    )

            log.info(
                "sync_policies_tenant_done",
                tenant=tenant.name,
                totals=totals,
                reaped=reaped,
            )

    log.info("sync_policies_complete", totals=totals, attachments=attachments)
    return {"policies": totals, "attachments": attachments}
