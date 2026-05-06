"""Shared utilities for Celery tasks."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Tenant


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a DB session with commit/rollback handling."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def iter_tenants(db: Session) -> list[Tenant]:
    """Return all tenants. v1 has one row; multi-tenant-ready."""
    return list(db.execute(select(Tenant)).scalars().all())
