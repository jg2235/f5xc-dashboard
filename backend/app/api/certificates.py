"""Certificate read endpoints with expiry classification."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.db import get_db
from app.f5xc.transformers import classify_cert_status
from app.models import Certificate, User
from app.schemas.certificate import CertificateOut, CertificateStats, CertificateSummary

router = APIRouter()


def _to_summary(cert: Certificate, warn_days: int, critical_days: int) -> CertificateSummary:
    status, days = classify_cert_status(cert.not_after, warn_days=warn_days, critical_days=critical_days)
    return CertificateSummary(
        id=cert.id,
        namespace=cert.namespace,
        name=cert.name,
        subject=cert.subject,
        issuer=cert.issuer,
        san_dns=cert.san_dns,
        not_before=cert.not_before,
        not_after=cert.not_after,
        auto_cert=cert.auto_cert,
        days_until_expiry=days,
        status=status,  # type: ignore[arg-type]
        last_seen_at=cert.last_seen_at,
    )


@router.get("", response_model=list[CertificateSummary], summary="List certificates")
def list_certs(
    status_filter: str | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CertificateSummary]:
    settings = get_settings()
    stmt = (
        select(Certificate)
        .where(Certificate.tenant_id == user.tenant_id)
        .order_by(Certificate.not_after.nulls_last())
    )
    rows = db.execute(stmt).scalars().all()
    summaries = [_to_summary(c, settings.cert_warn_days, settings.cert_critical_days) for c in rows]
    if status_filter:
        summaries = [s for s in summaries if s.status == status_filter]
    return summaries


@router.get("/stats", response_model=CertificateStats, summary="Cert expiration stats")
def cert_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CertificateStats:
    settings = get_settings()
    rows = db.execute(
        select(Certificate).where(Certificate.tenant_id == user.tenant_id)
    ).scalars().all()

    counts = {"ok": 0, "warn": 0, "critical": 0, "expired": 0, "unknown": 0}
    for cert in rows:
        status, _ = classify_cert_status(
            cert.not_after,
            warn_days=settings.cert_warn_days,
            critical_days=settings.cert_critical_days,
        )
        counts[status] += 1

    return CertificateStats(
        total=len(rows),
        ok=counts["ok"],
        warn=counts["warn"],
        critical=counts["critical"],
        expired=counts["expired"],
    )


@router.get("/{cert_id}", response_model=CertificateOut, summary="Get certificate by id")
def get_cert(
    cert_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CertificateOut:
    settings = get_settings()
    cert = db.get(Certificate, cert_id)
    if cert is None or cert.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Certificate not found")
    base = _to_summary(cert, settings.cert_warn_days, settings.cert_critical_days)
    return CertificateOut(
        **base.model_dump(),
        raw_spec=cert.raw_spec,
        serial_number=cert.serial_number,
        fingerprint_sha256=cert.fingerprint_sha256,
    )


# Silence unused import warning in case static analyzers complain
_ = datetime, timezone
