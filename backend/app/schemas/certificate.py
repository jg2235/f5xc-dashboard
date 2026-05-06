"""Certificate API schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

CertStatus = Literal["ok", "warn", "critical", "expired", "unknown"]


class CertificateSummary(BaseModel):
    id: uuid.UUID
    namespace: str
    name: str
    subject: str | None
    issuer: str | None
    san_dns: list[str]
    not_before: datetime | None
    not_after: datetime | None
    auto_cert: bool
    days_until_expiry: int | None
    status: CertStatus
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class CertificateOut(CertificateSummary):
    raw_spec: dict[str, Any]
    serial_number: str | None = None
    fingerprint_sha256: str | None = None


class CertificateStats(BaseModel):
    total: int
    ok: int
    warn: int
    critical: int
    expired: int
