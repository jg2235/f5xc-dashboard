"""Liveness + readiness."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter()


@router.get("/healthz", summary="Liveness")
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness (DB reachable)")
def readyz(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ready"}
