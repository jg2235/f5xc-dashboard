"""Sync certificate_chains from F5 XC → DB. Parses PEM to extract not_after."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.f5xc.client import F5XCClient
from app.f5xc.transformers import extract_cert_fields
from app.logging_config import get_logger
from app.models import Certificate, LoadBalancer
from app.workers.celery_app import celery_app
from app.workers.tasks._common import iter_tenants, session_scope

log = get_logger(__name__)


def _parse_iso8601(value: str | None) -> datetime | None:
    """Best-effort ISO-8601 parser. Returns timezone-aware UTC datetime."""
    if not value:
        return None
    try:
        # Handle Z suffix; fromisoformat in 3.12 accepts it
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _materialize_auto_cert_from_lbs(db, tenant_id, sync_started_at: datetime) -> int:
    """Synthesize Certificate rows from LBs using https_auto_cert.

    F5 XC's https_auto_cert mode (Volterra-managed Let's Encrypt) doesn't
    create a corresponding certificate_chains object — the cert metadata
    lives only on the LB under spec.auto_cert_info. To make these certs
    visible in the certificates list and the expiration dashboard,
    synthesize one Certificate row per LB.

    Synthetic certs:
    - namespace = LB's namespace
    - name = "{lb_name}-auto-cert" (deterministic, idempotent)
    - auto_cert = True (already a column, used by frontend to badge)
    - raw_spec carries `synthesized_from_lb` for traceability
    """
    lbs = db.execute(
        select(LoadBalancer).where(LoadBalancer.tenant_id == tenant_id)
    ).scalars().all()
    inserted = 0
    for lb in lbs:
        spec = lb.raw_spec or {}
        if "https_auto_cert" not in spec or not spec.get("https_auto_cert"):
            continue
        info = spec.get("auto_cert_info") or {}
        subject = info.get("auto_cert_subject")
        issuer = info.get("auto_cert_issuer")
        not_after = _parse_iso8601(info.get("auto_cert_expiry"))
        if subject is None and not_after is None:
            # No useful info to synthesize from; skip silently
            continue
        cert_name = f"{lb.name}-auto-cert"
        san_dns: list[str] = []
        # Pull SANs from LB.domains as a sensible default
        if isinstance(lb.domains, list):
            san_dns = [d for d in lb.domains if isinstance(d, str)]
        stmt = insert(Certificate).values(
            tenant_id=tenant_id,
            namespace=lb.namespace,
            name=cert_name,
            subject=subject,
            issuer=issuer,
            san_dns=san_dns,
            not_before=None,
            not_after=not_after,
            serial_number=None,
            fingerprint_sha256=None,
            auto_cert=True,
            raw_spec={
                "synthesized_from_lb": lb.name,
                "auto_cert_info": info,
            },
            last_seen_at=sync_started_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["tenant_id", "namespace", "name"],
            set_={
                "subject": stmt.excluded.subject,
                "issuer": stmt.excluded.issuer,
                "san_dns": stmt.excluded.san_dns,
                "not_after": stmt.excluded.not_after,
                "auto_cert": stmt.excluded.auto_cert,
                "raw_spec": stmt.excluded.raw_spec,
                "last_seen_at": stmt.excluded.last_seen_at,
            },
        )
        db.execute(stmt)
        inserted += 1
    return inserted


@celery_app.task(name="app.workers.tasks.sync_certificates.sync_certificates")
def sync_certificates() -> dict:
    settings = get_settings()
    total = 0
    with session_scope() as db:
        tenants = iter_tenants(db)
        if not tenants:
            log.warning("sync_certificates_no_tenants")
            return {"tenants": 0, "certificates": 0}

        for tenant in tenants:
            # v0.9.0 — namespaces are operator-configured via tenant.namespaces.
            # The operator decides which namespaces to watch (commonly shared
            # + user namespace, but configurable to any list). The hardcoded
            # ["shared", f5xc_namespace] literal that lived here pre-v0.9.0
            # is now expressed as the operator's explicit list.
            namespaces_to_query = tenant.effective_namespaces

            sync_started_at = datetime.now(UTC)
            successful_sources = 0  # count of namespaces that listed OK + 1 if synthetic ran
            with F5XCClient(
                tenant=tenant.f5xc_tenant,
                api_token=settings.f5xc_api_token or tenant.f5xc_api_token,
                namespace=tenant.f5xc_namespace,
                mock=settings.f5xc_mock,
                timeout=settings.f5xc_request_timeout_seconds,
                max_retries=settings.f5xc_max_retries,
                api_url_template=settings.f5xc_api_url_template,
            ) as client:
                tenant_total = 0
                for ns in namespaces_to_query:
                    try:
                        listed = client.list_certificate_chains(namespace=ns)
                    except Exception as e:
                        # Don't crash the whole task if one namespace returns 401/403/etc.
                        # `shared` access varies by token RBAC.
                        log.warning(
                            "sync_certificates_namespace_failed",
                            namespace=ns,
                            error=str(e),
                        )
                        continue
                    successful_sources += 1

                    # sync_started_at hoisted to per-tenant scope (defined above)
                    items_count = 0
                    for stub in listed:
                        name = stub.get("name", "")
                        namespace = stub.get("namespace") or ns
                        if not name:
                            continue
                        # Per-cert detail GET — list returns metadata only.
                        try:
                            detail = client.get_certificate_chain(name=name, namespace=namespace)
                        except Exception as e:
                            log.warning(
                                "cert_detail_fetch_failed",
                                name=name, namespace=namespace, error=str(e),
                            )
                            continue
                        spec = detail.get("spec") or detail.get("get_spec") or {}
                        fields = extract_cert_fields(spec)
                        items_count += 1

                        stmt = insert(Certificate).values(
                            tenant_id=tenant.id,
                            namespace=namespace,
                            name=name,
                            subject=fields["subject"],
                            issuer=fields["issuer"],
                            san_dns=fields["san_dns"],
                            not_before=fields["not_before"],
                            not_after=fields["not_after"],
                            serial_number=fields["serial_number"],
                            fingerprint_sha256=fields["fingerprint_sha256"],
                            auto_cert=fields["auto_cert"],
                            raw_spec=spec,
                            last_seen_at=sync_started_at,
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["tenant_id", "namespace", "name"],
                            set_={
                                "subject": stmt.excluded.subject,
                                "issuer": stmt.excluded.issuer,
                                "san_dns": stmt.excluded.san_dns,
                                "not_before": stmt.excluded.not_before,
                                "not_after": stmt.excluded.not_after,
                                "serial_number": stmt.excluded.serial_number,
                                "fingerprint_sha256": stmt.excluded.fingerprint_sha256,
                                "auto_cert": stmt.excluded.auto_cert,
                                "raw_spec": stmt.excluded.raw_spec,
                                "last_seen_at": stmt.excluded.last_seen_at,
                            },
                        )
                        db.execute(stmt)
                        tenant_total += 1
                        total += 1

                    log.info(
                        "sync_certificates_namespace_done",
                        tenant=tenant.name,
                        namespace=ns,
                        count=items_count,
                    )

            # Synthesize certificates from LBs that use https_auto_cert.
            # Must run AFTER LB sync — depends on load_balancers.raw_spec.
            synthetic_count = _materialize_auto_cert_from_lbs(db, tenant.id, sync_started_at)
            if synthetic_count:
                total += synthetic_count
                log.info(
                    "sync_certificates_synthetic_done",
                    tenant=tenant.name,
                    count=synthetic_count,
                )
                successful_sources += 1

            # v0.8.0 — stale-row reaping. Reap by tenant only (covers shared +
            # user namespace + synthetic auto-certs, all share the same
            # tenant_id). Guarded on successful_sources > 0: if every list
            # call threw AND there were no LBs for synthesis, treat as failure
            # and reap nothing.
            reaped = 0
            if successful_sources > 0:
                reaped = db.execute(
                    delete(Certificate).where(
                        Certificate.tenant_id == tenant.id,
                        Certificate.last_seen_at < sync_started_at,
                    )
                ).rowcount or 0
                if reaped:
                    log.info(
                        "sync_certificates_reaped_stale",
                        tenant=tenant.name,
                        count=reaped,
                    )

            log.info(
                "sync_certificates_tenant_done",
                tenant=tenant.name,
                count=tenant_total,
                synthetic=synthetic_count,
                reaped=reaped,
            )
    log.info("sync_certificates_complete", total=total)
    return {"certificates": total}
