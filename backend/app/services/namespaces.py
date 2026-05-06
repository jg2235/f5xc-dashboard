"""Namespace CRUD service for the dashboard's singleton tenant.

The dashboard authenticates against ONE F5 XC tenant with ONE token, but
watches MULTIPLE namespaces within that tenant. This module manages the
list of watched namespaces.

Operations:
    list_namespaces() -> list[str]
    add_namespace(namespace) -> list[str]    # probes F5 XC, then appends
    remove_namespace(namespace) -> list[str] # refuses to leave empty
    replace_namespaces(list) -> list[str]    # bulk replace (probes each)

Probe-on-add: every add operation issues a list_load_balancers call against
the candidate namespace. If F5 XC rejects it (401, 403, 404, 5xx, timeout),
the add fails with NamespaceProbeError. Catches typos and bad RBAC at
write time, not at the next sync cycle.

LastNamespaceError protection: refuses to remove the only remaining
namespace. The dashboard would have nothing to sync. The CLI surfaces this
as exit code 1 with a clear error message; operator can use replace_namespaces
to swap out the last namespace if they really mean to.

Caller commits. The service flushes but does not commit, matching the
project pattern (api/admin_*.py and tenant_cli/user_cli all commit explicitly).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.f5xc.client import F5XCClient, F5XCError
from app.logging_config import get_logger
from app.models import Tenant

log = get_logger(__name__)


class NamespaceServiceError(Exception):
    pass


class NamespaceAlreadyPresent(NamespaceServiceError):
    pass


class NamespaceNotPresent(NamespaceServiceError):
    pass


class LastNamespaceError(NamespaceServiceError):
    """Refuse to leave the tenant with an empty namespace list."""


class NamespaceProbeError(NamespaceServiceError):
    """Probe-on-add call to F5 XC failed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _get_singleton_tenant(db: Session) -> Tenant:
    """The dashboard has exactly one tenant row. Fetch it.

    If for some reason there are zero or multiple tenants, raise — that's
    a state bug, not a normal failure mode.
    """
    tenants = db.execute(select(Tenant)).scalars().all()
    if len(tenants) == 0:
        raise NamespaceServiceError("no tenant row exists; run `make seed` first")
    if len(tenants) > 1:
        raise NamespaceServiceError(
            f"unexpected: {len(tenants)} tenant rows; dashboard expects exactly 1"
        )
    return tenants[0]


def _probe_namespace(*, f5xc_tenant: str, namespace: str, api_token: str) -> None:
    """Validate the namespace exists in F5 XC.

    Uses GET /api/web/namespaces/{name} — F5 XC's namespace registry endpoint,
    which is STRICT about existence (404s on bogus names). List-style
    endpoints like list_http_load_balancers return 200+empty for non-
    existent namespaces and don't catch typos.

    Any error → NamespaceProbeError with structured detail.
    """
    settings = get_settings()
    try:
        with F5XCClient(
            tenant=f5xc_tenant,
            api_token=api_token,
            namespace=namespace,
            mock=False,
            timeout=5.0,
            max_retries=0,
            api_url_template=settings.f5xc_api_url_template,
        ) as client:
            client.get_namespace_metadata(namespace)
    except F5XCError as e:
        raise NamespaceProbeError(
            f"F5 XC rejected namespace probe: HTTP {e.status_code}: {e}",
            status_code=e.status_code,
        ) from e
    except Exception as e:
        raise NamespaceProbeError(
            f"F5 XC namespace probe failed: {type(e).__name__}: {e}"
        ) from e


def list_namespaces(db: Session) -> list[str]:
    """Return the current namespace list (effective_namespaces with fallback)."""
    tenant = _get_singleton_tenant(db)
    return tenant.effective_namespaces


def add_namespace(db: Session, namespace: str) -> list[str]:
    """Probe + append. Returns the updated namespace list. Caller commits."""
    namespace = namespace.strip()
    if not namespace:
        raise NamespaceServiceError("namespace cannot be empty")
    if len(namespace) > 120:
        raise NamespaceServiceError(f"namespace too long ({len(namespace)} > 120 chars)")

    tenant = _get_singleton_tenant(db)
    current = tenant.effective_namespaces
    if namespace in current:
        raise NamespaceAlreadyPresent(
            f"namespace {namespace!r} already in list ({current!r})"
        )

    settings = get_settings()
    api_token = settings.f5xc_api_token or tenant.f5xc_api_token
    if not api_token:
        raise NamespaceServiceError(
            "no F5 XC token configured (set F5XC_API_TOKEN env or tenant.f5xc_api_token)"
        )

    log.info(
        "namespace_add_probe",
        tenant=tenant.f5xc_tenant, namespace=namespace,
    )
    _probe_namespace(
        f5xc_tenant=tenant.f5xc_tenant,
        namespace=namespace,
        api_token=api_token,
    )

    new_list = list(current) + [namespace]
    tenant.namespaces = new_list
    db.flush()
    log.info("namespace_added", tenant=tenant.name, namespace=namespace, total=len(new_list))
    return new_list


def remove_namespace(db: Session, namespace: str) -> list[str]:
    """Remove from list. Refuses to leave empty. Returns updated list."""
    namespace = namespace.strip()
    tenant = _get_singleton_tenant(db)
    current = tenant.effective_namespaces

    if namespace not in current:
        raise NamespaceNotPresent(
            f"namespace {namespace!r} not in current list ({current!r})"
        )

    if len(current) == 1:
        raise LastNamespaceError(
            f"refusing to remove last namespace {namespace!r}; "
            "use replace_namespaces to swap if intentional"
        )

    new_list = [n for n in current if n != namespace]
    tenant.namespaces = new_list
    db.flush()
    log.info(
        "namespace_removed",
        tenant=tenant.name, namespace=namespace, remaining=len(new_list),
    )
    return new_list


def replace_namespaces(db: Session, namespaces: list[str]) -> list[str]:
    """Bulk replace. Probes each new namespace. Refuses empty list."""
    namespaces = [n.strip() for n in namespaces if n and n.strip()]
    if not namespaces:
        raise LastNamespaceError("cannot replace with empty list")
    if len(set(namespaces)) != len(namespaces):
        raise NamespaceServiceError(f"duplicate namespaces: {namespaces}")

    tenant = _get_singleton_tenant(db)
    current = tenant.effective_namespaces
    settings = get_settings()
    api_token = settings.f5xc_api_token or tenant.f5xc_api_token
    if not api_token:
        raise NamespaceServiceError("no F5 XC token configured")

    # Probe ONLY the namespaces being added (not existing ones — they were
    # already probed when first added or seeded).
    new_namespaces = [n for n in namespaces if n not in current]
    for ns in new_namespaces:
        log.info("namespace_replace_probe", namespace=ns)
        _probe_namespace(
            f5xc_tenant=tenant.f5xc_tenant,
            namespace=ns,
            api_token=api_token,
        )

    tenant.namespaces = namespaces
    db.flush()
    log.info(
        "namespaces_replaced",
        tenant=tenant.name, old=current, new=namespaces,
    )
    return namespaces


__all__ = [
    "NamespaceServiceError",
    "NamespaceAlreadyPresent",
    "NamespaceNotPresent",
    "LastNamespaceError",
    "NamespaceProbeError",
    "list_namespaces",
    "add_namespace",
    "remove_namespace",
    "replace_namespaces",
]
