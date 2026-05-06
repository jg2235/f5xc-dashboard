"""Alert rule engine (slice 7).

Each rule is a callable that returns zero or more `AlertCandidate` objects
for a tenant. The engine upserts them into the alerts table with dedup
by (tenant_id, rule_id, dedupe_key). Re-firing bumps occurrence_count and
last_seen_at; first_seen_at preserved.

Rules in the default set:
  - waf.block_burst         WAF blocks > N per minute on a single LB
  - waf.new_attacker        new IP appearing in WAF top-K (state change)
  - bot.cred_stuffing       challenge_failed rate > 50% in 5-min window per IP
  - api.state_change        ML state transition (info)
  - api.shadow_emergence    new shadow endpoint with > N samples
  - cert.expiry             cert expires in < N days

Each rule is enabled/disabled via per-rule .env flag. Rules are pure
functions of (db, settings, tenant) — testable in isolation.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, desc, distinct, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.logging_config import get_logger
from app.models import (
    Alert,
    ApiDiscoveryState,
    ApiEndpoint,
    BotEvent,
    Certificate,
    Tenant,
    WafEvent,
    WafMetric1Min,
)

log = get_logger(__name__)


@dataclass
class AlertCandidate:
    rule_id: str
    severity: str  # critical | warning | info
    dedupe_key: str
    title: str
    description: str = ""
    context: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


def rule_waf_block_burst(
    db: Session, settings: Settings, tenant: Tenant,
) -> Iterable[AlertCandidate]:
    """WAF blocks/min for a single LB exceeded threshold in last 5 min.

    Reads from waf_metrics_1min (cheap pre-aggregated counts).
    Dedupe key: lb:{namespace}/{lb_name} — repeats for the same LB merge.
    """
    end = datetime.now(UTC)
    start = end - timedelta(minutes=5)
    rows = db.execute(
        select(
            WafMetric1Min.lb_namespace, WafMetric1Min.lb_name,
            func.max(WafMetric1Min.blocked_count).label("peak"),
        )
        .where(
            WafMetric1Min.tenant_id == tenant.id,
            WafMetric1Min.bucket_time >= start,
            WafMetric1Min.bucket_time <= end,
        )
        .group_by(WafMetric1Min.lb_namespace, WafMetric1Min.lb_name)
        .having(func.max(WafMetric1Min.blocked_count) >= settings.alert_waf_block_burst_threshold)
    ).all()

    for r in rows:
        yield AlertCandidate(
            rule_id="waf.block_burst",
            severity="warning",
            dedupe_key=f"lb:{r.lb_namespace}/{r.lb_name}",
            title=f"WAF block burst on {r.lb_name}",
            description=(
                f"Peak {int(r.peak)} blocks/min on {r.lb_name} in last 5 minutes "
                f"(threshold {settings.alert_waf_block_burst_threshold})."
            ),
            context={
                "lb_namespace": r.lb_namespace,
                "lb_name": r.lb_name,
                "peak_blocks_per_min": int(r.peak),
                "threshold": settings.alert_waf_block_burst_threshold,
            },
        )


def rule_waf_new_attacker(
    db: Session, settings: Settings, tenant: Tenant,
) -> Iterable[AlertCandidate]:
    """New IP appearing in top-K WAF blockers in last 1h that wasn't there in
    the previous 24h window (state change detection).

    Dedupe key: ip:{source_ip} — same IP doesn't re-alert.
    """
    now = datetime.now(UTC)
    recent_start = now - timedelta(hours=1)
    prior_start = now - timedelta(hours=25)
    prior_end = now - timedelta(hours=1)

    # Top 10 attacker IPs by WAF block count in the last hour
    recent_rows = db.execute(
        select(
            WafEvent.source_ip,
            WafEvent.source_country,
            WafEvent.source_asn,
            func.count().label("c"),
        )
        .where(
            WafEvent.tenant_id == tenant.id,
            WafEvent.event_time >= recent_start,
            WafEvent.action == "BLOCK",
            WafEvent.source_ip.is_not(None),
        )
        .group_by(WafEvent.source_ip, WafEvent.source_country, WafEvent.source_asn)
        .order_by(desc("c"))
        .limit(10)
    ).all()

    if not recent_rows:
        return

    recent_ips = {r.source_ip for r in recent_rows}
    prior_ips = {
        row[0] for row in db.execute(
            select(distinct(WafEvent.source_ip))
            .where(
                WafEvent.tenant_id == tenant.id,
                WafEvent.event_time >= prior_start,
                WafEvent.event_time < prior_end,
                WafEvent.action == "BLOCK",
                WafEvent.source_ip.in_(recent_ips),
            )
        ).all()
    }

    new_ips = recent_ips - prior_ips
    for r in recent_rows:
        if r.source_ip not in new_ips:
            continue
        yield AlertCandidate(
            rule_id="waf.new_attacker",
            severity="info",
            dedupe_key=f"ip:{r.source_ip}",
            title=f"New WAF attacker: {r.source_ip}",
            description=(
                f"Source IP {r.source_ip} ({r.source_country or 'unknown'}, "
                f"AS{r.source_asn or '?'}) entered the top-10 with {int(r.c)} blocks "
                f"in the last hour — not seen in prior 24h window."
            ),
            context={
                "source_ip": r.source_ip,
                "source_country": r.source_country,
                "source_asn": r.source_asn,
                "block_count": int(r.c),
            },
        )


def rule_bot_cred_stuffing(
    db: Session, settings: Settings, tenant: Tenant,
) -> Iterable[AlertCandidate]:
    """Per-IP credential-stuffing pattern: high challenge_failed rate.

    Dedupe key: ip:{source_ip}
    """
    end = datetime.now(UTC)
    start = end - timedelta(minutes=10)
    rows = db.execute(
        select(
            BotEvent.source_ip, BotEvent.source_country, BotEvent.source_asn,
            func.count().label("total"),
            func.sum(
                case(
                    (BotEvent.challenge_result == "failed", 1),
                    else_=0,
                )
            ).label("failed"),
            func.max(BotEvent.endpoint_path).label("any_endpoint"),
        )
        .where(
            BotEvent.tenant_id == tenant.id,
            BotEvent.event_time >= start,
            BotEvent.source_ip.is_not(None),
            BotEvent.action.in_(("CHALLENGE", "BLOCK")),
        )
        .group_by(BotEvent.source_ip, BotEvent.source_country, BotEvent.source_asn)
        .having(func.count() >= settings.alert_bot_cred_stuff_min_events)
    ).all()

    threshold_pct = settings.alert_bot_cred_stuff_failure_pct
    for r in rows:
        total = int(r.total)
        failed = int(r.failed or 0)
        failure_pct = (failed / total) * 100 if total > 0 else 0
        if failure_pct < threshold_pct:
            continue
        yield AlertCandidate(
            rule_id="bot.cred_stuffing",
            severity="critical",
            dedupe_key=f"ip:{r.source_ip}",
            title=f"Suspected credential stuffing from {r.source_ip}",
            description=(
                f"{failed}/{total} bot challenges failed ({failure_pct:.0f}%) "
                f"in last 10 min from {r.source_ip} "
                f"({r.source_country or 'unknown'})."
            ),
            context={
                "source_ip": r.source_ip,
                "source_country": r.source_country,
                "source_asn": r.source_asn,
                "total_attempts": total,
                "failed_challenges": failed,
                "failure_pct": round(failure_pct, 1),
                "endpoint_sample": r.any_endpoint,
            },
        )


def rule_api_state_change(
    db: Session, settings: Settings, tenant: Tenant,
) -> Iterable[AlertCandidate]:
    """API discovery state changed in last cycle (info).

    state_changed_at is updated by F5 XC each time the ML lifecycle moves.
    We alert on transitions detected within the last poll interval (default
    10 min). Dedupe key: lb:{namespace}/{lb_name}:{state} — re-entering the
    same state could happen, each entry alerts once until manually resolved.
    """
    end = datetime.now(UTC)
    start = end - timedelta(minutes=settings.poll_config_interval / 60 + 1)

    rows = db.execute(
        select(ApiDiscoveryState).where(
            ApiDiscoveryState.tenant_id == tenant.id,
            ApiDiscoveryState.state_changed_at.is_not(None),
            ApiDiscoveryState.state_changed_at >= start,
        )
    ).scalars().all()

    for r in rows:
        yield AlertCandidate(
            rule_id="api.state_change",
            severity="info",
            dedupe_key=f"lb:{r.lb_namespace}/{r.lb_name}:{r.state}",
            title=f"API discovery on {r.lb_name} → {r.state}",
            description=(
                f"ML model state changed to '{r.state}' on {r.lb_name} "
                f"(confidence {r.confidence_score or '?'}%, "
                f"{r.total_endpoints_discovered} endpoints discovered)."
            ),
            context={
                "lb_namespace": r.lb_namespace,
                "lb_name": r.lb_name,
                "state": r.state,
                "confidence_score": r.confidence_score,
                "endpoints": r.total_endpoints_discovered,
            },
        )


def rule_api_shadow_emergence(
    db: Session, settings: Settings, tenant: Tenant,
) -> Iterable[AlertCandidate]:
    """Newly-emerged shadow endpoint with growing traffic.

    Triggers when a SHADOW endpoint accumulates >= alert_api_shadow_emergence_samples
    samples since first seen, AND first_seen_at is within the last 24h.
    Dedupe key: ep:{lb_name}:{method}:{path}
    """
    horizon = datetime.now(UTC) - timedelta(hours=24)
    rows = db.execute(
        select(ApiEndpoint).where(
            ApiEndpoint.tenant_id == tenant.id,
            ApiEndpoint.is_shadow.is_(True),
            ApiEndpoint.first_seen_at.is_not(None),
            ApiEndpoint.first_seen_at >= horizon,
            ApiEndpoint.total_request_samples >= settings.alert_api_shadow_emergence_samples,
        )
    ).scalars().all()

    for r in rows:
        yield AlertCandidate(
            rule_id="api.shadow_emergence",
            severity="warning",
            dedupe_key=f"ep:{r.lb_name}:{r.method}:{r.endpoint_path}",
            title=f"New shadow endpoint: {r.method} {r.endpoint_path}",
            description=(
                f"{r.total_request_samples} requests to undeclared endpoint "
                f"{r.method} {r.endpoint_path} on {r.lb_name} "
                f"in the last 24h. Auth: {r.auth_type or 'unknown'}."
            ),
            context={
                "endpoint_id": str(r.id),
                "lb_name": r.lb_name,
                "method": r.method,
                "path": r.endpoint_path,
                "samples": r.total_request_samples,
                "auth_type": r.auth_type,
            },
        )


def rule_cert_expiry(
    db: Session, settings: Settings, tenant: Tenant,
) -> Iterable[AlertCandidate]:
    """Cert expiring within critical threshold.

    Dedupe key: cert:{namespace}:{name}
    """
    horizon = datetime.now(UTC) + timedelta(days=settings.alert_cert_expiry_critical_days)
    rows = db.execute(
        select(Certificate).where(
            Certificate.tenant_id == tenant.id,
            Certificate.not_after.is_not(None),
            Certificate.not_after <= horizon,
        )
    ).scalars().all()

    for r in rows:
        days_left = (r.not_after - datetime.now(UTC)).days if r.not_after else None
        is_expired = days_left is not None and days_left < 0
        severity = "critical" if (is_expired or (days_left is not None and days_left <= 1)) else "warning"
        yield AlertCandidate(
            rule_id="cert.expiry",
            severity=severity,
            dedupe_key=f"cert:{r.namespace}:{r.name}",
            title=(
                f"Certificate {'expired' if is_expired else 'expiring soon'}: {r.name}"
            ),
            description=(
                f"Certificate {r.name} in namespace {r.namespace} "
                + (
                    f"expired {abs(days_left)} day(s) ago." if is_expired
                    else f"expires in {days_left} day(s)."
                )
            ),
            context={
                "namespace": r.namespace,
                "name": r.name,
                "not_after": r.not_after.isoformat() if r.not_after else None,
                "days_until_expiry": days_left,
            },
        )


# ---------------------------------------------------------------------------
# Engine — register, evaluate, upsert
# ---------------------------------------------------------------------------


def get_enabled_rules(settings: Settings) -> list:
    rules = []
    if settings.alert_rule_waf_burst_enabled:
        rules.append(rule_waf_block_burst)
    if settings.alert_rule_waf_new_attacker_enabled:
        rules.append(rule_waf_new_attacker)
    if settings.alert_rule_bot_cred_stuff_enabled:
        rules.append(rule_bot_cred_stuffing)
    if settings.alert_rule_api_state_change_enabled:
        rules.append(rule_api_state_change)
    if settings.alert_rule_api_shadow_enabled:
        rules.append(rule_api_shadow_emergence)
    if settings.alert_rule_cert_expiry_enabled:
        rules.append(rule_cert_expiry)
    return rules


def upsert_alert(db: Session, *, tenant_id: uuid.UUID, candidate: AlertCandidate) -> str:
    """Upsert alert candidate. Returns 'new' or 'duplicate' for telemetry."""
    now = datetime.now(UTC)
    stmt = insert(Alert).values(
        tenant_id=tenant_id,
        rule_id=candidate.rule_id,
        severity=candidate.severity,
        status="open",
        dedupe_key=candidate.dedupe_key,
        title=candidate.title,
        description=candidate.description,
        context=candidate.context,
        occurrence_count=1,
        first_seen_at=now,
        last_seen_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_alert_dedup_identity",
        set_={
            # Update mutable fields only — preserve first_seen_at, status, ack/resolve
            "severity": stmt.excluded.severity,
            "title": stmt.excluded.title,
            "description": stmt.excluded.description,
            "context": stmt.excluded.context,
            "occurrence_count": Alert.occurrence_count + 1,
            "last_seen_at": stmt.excluded.last_seen_at,
        },
    )
    db.execute(stmt)
    return "upserted"


def evaluate_all_rules(
    db: Session, settings: Settings, tenant: Tenant,
) -> dict[str, int]:
    """Run every enabled rule, upsert candidates. Returns {rule_id: count}."""
    counts: dict[str, int] = {}
    for rule in get_enabled_rules(settings):
        try:
            for candidate in rule(db, settings, tenant):
                upsert_alert(db, tenant_id=tenant.id, candidate=candidate)
                counts[candidate.rule_id] = counts.get(candidate.rule_id, 0) + 1
        except Exception:  # noqa: BLE001 — one rule's failure shouldn't kill the others
            log.exception("alert_rule_failed", rule=rule.__name__)
    return counts
