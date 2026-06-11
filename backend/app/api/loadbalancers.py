"""Load balancer read endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models import (
    ApiDefinition,
    AppFirewall,
    BotDefensePolicy,
    LoadBalancer,
    OriginPool,
    PolicyAttachment,
    ServicePolicy,
    User,
)
from app.schemas.loadbalancer import (
    LoadBalancerDetail,
    LoadBalancerOut,
    LoadBalancerStats,
    LoadBalancerSummary,
)
from app.schemas.pool import OriginPoolSummary
from app.schemas.security import MaliciousUserSummary
from app.security.correlator import correlate_attackers

router = APIRouter()


def _risk_score(agg) -> int:
    """Heuristic 0–100 risk from the blocking/challenge mix.

    Weighted so active blocking dominates, then challenges, then monitor-only.
    Saturates at 100; any blocked request floors the score into the high band.
    """
    raw = (
        agg.waf_block * 12
        + agg.bot_block * 12
        + agg.bot_challenge * 6
        + agg.waf_monitor * 2
    )
    return min(100, raw)


def _severity(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


class AttachedPolicyRef(BaseModel):
    """A policy reference resolved from an LB → policy_attachments → policy table.

    Returned by /loadbalancers/{id}/policies — gives the frontend everything
    it needs to render a clickable list (the policy_id may be null if the
    referenced policy hasn't been synced yet — common just after sync_loadbalancers
    runs but before sync_policies catches up).
    """
    policy_type: str
    policy_namespace: str
    policy_name: str
    is_shared: bool
    policy_id: uuid.UUID | None = None


_POLICY_TYPE_TO_MODEL = {
    "app_firewall": AppFirewall,
    "service_policy": ServicePolicy,
    "bot_defense_policy": BotDefensePolicy,
    "api_definition": ApiDefinition,
}


@router.get("", response_model=list[LoadBalancerSummary], summary="List load balancers")
def list_lbs(
    namespace: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LoadBalancerSummary]:
    stmt = select(LoadBalancer).where(LoadBalancer.tenant_id == user.tenant_id)
    if namespace:
        stmt = stmt.where(LoadBalancer.namespace == namespace)
    stmt = stmt.order_by(LoadBalancer.namespace, LoadBalancer.name)
    rows = db.execute(stmt).scalars().all()
    return [LoadBalancerSummary.model_validate(r) for r in rows]


@router.get("/stats", response_model=LoadBalancerStats, summary="Aggregate LB stats")
def lb_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoadBalancerStats:
    def count_where(*conds) -> int:
        q = select(func.count()).select_from(LoadBalancer).where(
            LoadBalancer.tenant_id == user.tenant_id, *conds
        )
        return db.execute(q).scalar_one()

    total = db.execute(
        select(func.count()).select_from(LoadBalancer).where(LoadBalancer.tenant_id == user.tenant_id)
    ).scalar_one()

    return LoadBalancerStats(
        total=total,
        with_waf=count_where(LoadBalancer.has_waf.is_(True)),
        with_bot_defense=count_where(LoadBalancer.has_bot_defense.is_(True)),
        with_api_protection=count_where(LoadBalancer.has_api_protection.is_(True)),
        with_service_policy=count_where(LoadBalancer.has_service_policy.is_(True)),
        https=count_where(LoadBalancer.lb_type == "https"),
        http_only=count_where(LoadBalancer.lb_type == "http"),
    )


@router.get("/{lb_id}", response_model=LoadBalancerDetail, summary="LB detail")
def get_lb(
    lb_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoadBalancerDetail:
    lb = db.get(LoadBalancer, lb_id)
    if lb is None or lb.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Load balancer not found")

    pools_query = (
        select(OriginPool)
        .where(
            OriginPool.tenant_id == user.tenant_id,
            OriginPool.name.in_(lb.origin_pool_refs) if lb.origin_pool_refs else False,  # type: ignore[arg-type]
        )
    )
    pools = db.execute(pools_query).scalars().all() if lb.origin_pool_refs else []

    return LoadBalancerDetail(
        id=lb.id,
        namespace=lb.namespace,
        name=lb.name,
        domains=lb.domains,
        lb_type=lb.lb_type,
        advertise_mode=lb.advertise_mode,
        advertised_sites=lb.advertised_sites,
        has_waf=lb.has_waf,
        has_service_policy=lb.has_service_policy,
        has_bot_defense=lb.has_bot_defense,
        has_api_protection=lb.has_api_protection,
        origin_pool_refs=lb.origin_pool_refs,
        cert_ref=lb.cert_ref,
        last_seen_at=lb.last_seen_at,
        raw_spec=lb.raw_spec,
        pools=[OriginPoolSummary.model_validate(p) for p in pools],
    )


@router.get(
    "/{lb_id}/policies",
    response_model=list[AttachedPolicyRef],
    summary="Policies attached to this LB",
)
def get_lb_policies(
    lb_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AttachedPolicyRef]:
    lb = db.get(LoadBalancer, lb_id)
    if lb is None or lb.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Load balancer not found")

    attachments = db.execute(
        select(PolicyAttachment).where(
            PolicyAttachment.tenant_id == user.tenant_id,
            PolicyAttachment.lb_id == lb_id,
        ).order_by(PolicyAttachment.policy_type, PolicyAttachment.policy_name)
    ).scalars().all()

    out: list[AttachedPolicyRef] = []
    for att in attachments:
        model = _POLICY_TYPE_TO_MODEL.get(att.policy_type)
        policy_id: uuid.UUID | None = None
        is_shared = att.policy_namespace == "shared"
        if model is not None:
            row = db.execute(
                select(model.id, model.is_shared).where(
                    model.tenant_id == user.tenant_id,
                    model.namespace == att.policy_namespace,
                    model.name == att.policy_name,
                )
            ).first()
            if row is not None:
                policy_id = row.id
                is_shared = bool(row.is_shared)
        out.append(AttachedPolicyRef(
            policy_type=att.policy_type,
            policy_namespace=att.policy_namespace,
            policy_name=att.policy_name,
            is_shared=is_shared,
            policy_id=policy_id,
        ))
    return out


@router.get(
    "/{lb_id}/malicious-users",
    response_model=list[MaliciousUserSummary],
    summary="Malicious source IPs scoped to this LB (WAF + Bot signals)",
)
def get_lb_malicious_users(
    lb_id: uuid.UUID,
    window_minutes: int = Query(default=1440, ge=5, le=10080),
    limit: int = Query(default=50, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MaliciousUserSummary]:
    """Per-LB "malicious users": source IPs blocked/challenged/monitored by this
    LB's WAF or Bot defense within the window, ranked by derived risk score.
    Mirrors F5 XC's Security Monitoring → Malicious Users tab."""
    from datetime import timedelta

    lb = db.get(LoadBalancer, lb_id)
    if lb is None or lb.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Load balancer not found")

    aggregates = correlate_attackers(
        db,
        tenant_id=user.tenant_id,
        window=timedelta(minutes=window_minutes),
        lb_namespace=lb.namespace,
        lb_name=lb.name,
    )

    rows: list[MaliciousUserSummary] = []
    for (ip, asn, country), agg in aggregates.items():
        score = _risk_score(agg)
        rows.append(MaliciousUserSummary(
            source_ip=ip,
            source_asn=asn,
            source_country=country,
            waf_block_count=agg.waf_block,
            waf_monitor_count=agg.waf_monitor,
            bot_block_count=agg.bot_block,
            bot_challenge_count=agg.bot_challenge,
            total_events=agg.total,
            top_endpoint=agg.top_endpoint,
            top_signature=agg.top_signature,
            risk_score=score,
            severity=_severity(score),
            first_seen_at=agg.first_seen,
            last_seen_at=agg.last_seen,
        ))

    rows.sort(key=lambda r: (r.risk_score, r.total_events), reverse=True)
    return rows[:limit]


@router.get("/{lb_id}/raw", response_model=LoadBalancerOut, summary="LB full raw record")
def get_lb_raw(
    lb_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoadBalancerOut:
    lb = db.get(LoadBalancer, lb_id)
    if lb is None or lb.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Load balancer not found")
    return LoadBalancerOut.model_validate(lb)
