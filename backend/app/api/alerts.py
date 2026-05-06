"""Alerts endpoints (slice 7).

  GET  /api/v1/alerts                   — list with filters
  GET  /api/v1/alerts/summary           — counts by severity + status
  GET  /api/v1/alerts/{id}              — single alert detail
  POST /api/v1/alerts/{id}/acknowledge  — ack
  POST /api/v1/alerts/{id}/resolve      — resolve
  POST /api/v1/alerts/{id}/reopen       — re-open a resolved/acked alert
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models import Alert, User
from app.schemas.security import AlertActionResult, AlertOut, AlertSummaryStats

router = APIRouter()


def _to_out(r: Alert) -> AlertOut:
    return AlertOut(
        id=str(r.id),
        rule_id=r.rule_id,
        severity=r.severity,
        status=r.status,
        dedupe_key=r.dedupe_key,
        title=r.title,
        description=r.description,
        context=r.context,
        occurrence_count=r.occurrence_count,
        first_seen_at=r.first_seen_at,
        last_seen_at=r.last_seen_at,
        acknowledged_at=r.acknowledged_at,
        resolved_at=r.resolved_at,
    )


@router.get("", response_model=list[AlertOut], summary="List alerts")
def list_alerts(
    status: Literal["all", "open", "acknowledged", "resolved"] = Query(default="open"),
    severity: Literal["all", "critical", "warning", "info"] = Query(default="all"),
    rule_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AlertOut]:
    stmt = select(Alert).where(Alert.tenant_id == user.tenant_id)
    if status != "all":
        stmt = stmt.where(Alert.status == status)
    if severity != "all":
        stmt = stmt.where(Alert.severity == severity)
    if rule_id:
        stmt = stmt.where(Alert.rule_id == rule_id)
    stmt = stmt.order_by(desc(Alert.last_seen_at)).limit(limit).offset(offset)
    return [_to_out(r) for r in db.execute(stmt).scalars().all()]


@router.get("/summary", response_model=AlertSummaryStats, summary="Alert counts")
def alert_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertSummaryStats:
    rows = db.execute(
        select(Alert.status, Alert.severity, func.count().label("c"))
        .where(Alert.tenant_id == user.tenant_id)
        .group_by(Alert.status, Alert.severity)
    ).all()
    counts: dict[tuple[str, str], int] = {}
    for r in rows:
        counts[(r.status, r.severity)] = int(r.c)
    return AlertSummaryStats(
        open=sum(c for (s, _), c in counts.items() if s == "open"),
        acknowledged=sum(c for (s, _), c in counts.items() if s == "acknowledged"),
        resolved=sum(c for (s, _), c in counts.items() if s == "resolved"),
        critical=sum(c for (s, sev), c in counts.items() if s == "open" and sev == "critical"),
        warning=sum(c for (s, sev), c in counts.items() if s == "open" and sev == "warning"),
        info=sum(c for (s, sev), c in counts.items() if s == "open" and sev == "info"),
    )


@router.get("/{alert_id}", response_model=AlertOut, summary="Alert detail")
def alert_detail(
    alert_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertOut:
    r = db.get(Alert, alert_id)
    if r is None or r.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _to_out(r)


def _transition(
    db: Session, user: User, alert_id: uuid.UUID, new_status: str,
) -> AlertActionResult:
    r = db.get(Alert, alert_id)
    if r is None or r.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Alert not found")

    now = datetime.now(UTC)
    if new_status == "acknowledged":
        r.status = "acknowledged"
        if r.acknowledged_at is None:
            r.acknowledged_at = now
    elif new_status == "resolved":
        r.status = "resolved"
        r.resolved_at = now
        if r.acknowledged_at is None:
            r.acknowledged_at = now
    elif new_status == "open":
        r.status = "open"
        r.acknowledged_at = None
        r.resolved_at = None
    else:
        raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")

    db.flush()
    return AlertActionResult(
        id=str(r.id),
        status=r.status,
        acknowledged_at=r.acknowledged_at,
        resolved_at=r.resolved_at,
    )


@router.post("/{alert_id}/acknowledge", response_model=AlertActionResult, summary="Acknowledge")
def acknowledge_alert(
    alert_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertActionResult:
    return _transition(db, user, alert_id, "acknowledged")


@router.post("/{alert_id}/resolve", response_model=AlertActionResult, summary="Resolve")
def resolve_alert(
    alert_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertActionResult:
    return _transition(db, user, alert_id, "resolved")


@router.post("/{alert_id}/reopen", response_model=AlertActionResult, summary="Reopen")
def reopen_alert(
    alert_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertActionResult:
    return _transition(db, user, alert_id, "open")
