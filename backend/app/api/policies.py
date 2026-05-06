"""Policy read endpoints (slice 3).

URL shape:
  GET /api/v1/policies/stats                              → aggregate counts
  GET /api/v1/policies/{type}                             → list (filterable)
  GET /api/v1/policies/{type}/{id}                        → detail with attached_to[]

Where {type} is one of:
  app_firewalls | service_policies | bot_defense_policies | api_definitions
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models import (
    ApiDefinition,
    AppFirewall,
    BotDefensePolicy,
    LoadBalancer,
    PolicyAttachment,
    ServicePolicy,
    User,
)
from app.schemas.policy import (
    ApiDefinitionDetail,
    ApiDefinitionSummary,
    AppFirewallDetail,
    AppFirewallSummary,
    BotDefensePolicyDetail,
    BotDefensePolicySummary,
    PolicyAttachmentRef,
    PolicyStats,
    PolicyTypeStats,
    ServicePolicyDetail,
    ServicePolicySummary,
)

router = APIRouter()

# URL-segment → (model, summary schema, detail schema, policy_type literal)
_TYPE_MAP: dict[str, tuple[Any, Any, Any, str]] = {
    "app_firewalls":         (AppFirewall, AppFirewallSummary, AppFirewallDetail, "app_firewall"),
    "service_policies":      (ServicePolicy, ServicePolicySummary, ServicePolicyDetail, "service_policy"),
    "bot_defense_policies":  (
        BotDefensePolicy, BotDefensePolicySummary, BotDefensePolicyDetail, "bot_defense_policy",
    ),
    "api_definitions":       (ApiDefinition, ApiDefinitionSummary, ApiDefinitionDetail, "api_definition"),
}


def _resolve_type(policy_type_url: str):
    if policy_type_url not in _TYPE_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown policy type '{policy_type_url}'. Valid: {sorted(_TYPE_MAP)}",
        )
    return _TYPE_MAP[policy_type_url]


def _attachments_for(
    db: Session, tenant_id: uuid.UUID, policy_type: str, namespace: str, name: str,
) -> list[PolicyAttachmentRef]:
    rows = db.execute(
        select(PolicyAttachment, LoadBalancer)
        .join(LoadBalancer, LoadBalancer.id == PolicyAttachment.lb_id)
        .where(
            PolicyAttachment.tenant_id == tenant_id,
            PolicyAttachment.policy_type == policy_type,
            PolicyAttachment.policy_namespace == namespace,
            PolicyAttachment.policy_name == name,
        )
    ).all()
    out: list[PolicyAttachmentRef] = []
    for _att, lb in rows:
        out.append(PolicyAttachmentRef(lb_id=lb.id, lb_name=lb.name, lb_namespace=lb.namespace))
    return out


def _stats_for(db: Session, tenant_id: uuid.UUID, model, policy_type: str) -> PolicyTypeStats:
    total = db.execute(
        select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
    ).scalar_one()
    shared = db.execute(
        select(func.count()).select_from(model).where(
            model.tenant_id == tenant_id, model.is_shared.is_(True)
        )
    ).scalar_one()
    local = total - shared
    # Unattached: count of (namespace, name) pairs that have NO PolicyAttachment row.
    attached_pairs_subq = (
        select(PolicyAttachment.policy_namespace, PolicyAttachment.policy_name)
        .where(
            PolicyAttachment.tenant_id == tenant_id,
            PolicyAttachment.policy_type == policy_type,
        )
        .distinct()
        .subquery()
    )
    attached_pairs = db.execute(select(attached_pairs_subq.c)).all()
    attached_set = {(r.policy_namespace, r.policy_name) for r in attached_pairs}
    all_rows = db.execute(
        select(model.namespace, model.name).where(model.tenant_id == tenant_id)
    ).all()
    unattached = sum(1 for r in all_rows if (r.namespace, r.name) not in attached_set)
    return PolicyTypeStats(total=total, shared=shared, local=local, unattached=unattached)


@router.get("/stats", response_model=PolicyStats, summary="Aggregate policy stats")
def policy_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PolicyStats:
    return PolicyStats(
        app_firewall=_stats_for(db, user.tenant_id, AppFirewall, "app_firewall"),
        service_policy=_stats_for(db, user.tenant_id, ServicePolicy, "service_policy"),
        bot_defense_policy=_stats_for(db, user.tenant_id, BotDefensePolicy, "bot_defense_policy"),
        api_definition=_stats_for(db, user.tenant_id, ApiDefinition, "api_definition"),
    )


@router.get("/{policy_type}", summary="List policies of given type")
def list_policies(
    policy_type: str,
    scope: str | None = Query(default=None, description="shared | local"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model, summary_cls, _detail_cls, _ptype = _resolve_type(policy_type)
    stmt = select(model).where(model.tenant_id == user.tenant_id)
    if scope == "shared":
        stmt = stmt.where(model.is_shared.is_(True))
    elif scope == "local":
        stmt = stmt.where(model.is_shared.is_(False))
    stmt = stmt.order_by(model.namespace, model.name)
    rows = db.execute(stmt).scalars().all()
    return [summary_cls.model_validate(r) for r in rows]


@router.get("/{policy_type}/{policy_id}", summary="Policy detail with attached_to[]")
def get_policy(
    policy_type: str,
    policy_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model, summary_cls, detail_cls, ptype = _resolve_type(policy_type)
    obj = db.get(model, policy_id)
    if obj is None or obj.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail=f"{policy_type} not found")

    attachments = _attachments_for(db, user.tenant_id, ptype, obj.namespace, obj.name)
    base = summary_cls.model_validate(obj).model_dump()
    detail_kwargs = {**base, "raw_spec": obj.raw_spec, "attached_to": attachments}

    # Per-type extra fields not on Summary
    if model is AppFirewall:
        detail_kwargs.update({
            "default_anonymization": obj.default_anonymization,
            "default_bot_setting": obj.default_bot_setting,
            "detection_settings": obj.detection_settings,
            "allowed_response_codes": obj.allowed_response_codes,
        })
    elif model is BotDefensePolicy:
        detail_kwargs["protected_paths"] = obj.protected_paths

    return detail_cls(**detail_kwargs)
