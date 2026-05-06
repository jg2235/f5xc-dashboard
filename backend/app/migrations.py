"""Apply Alembic migrations on startup.

Behavior:
  - Fresh DB (no `alembic_version` table, no domain tables)        → upgrade head
  - Existing v0.2.0 DB (domain tables exist, no `alembic_version`) → stamp 0001_baseline,
                                                                     then upgrade head
  - Already-tracked DB                                              → upgrade head (no-op
                                                                     if at head)
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from alembic import command
from alembic.config import Config
from app.logging_config import get_logger

log = get_logger(__name__)

# /app/alembic.ini at runtime in the container
_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"

# Tables whose presence indicates the DB was built by v0.2.0's create_all,
# i.e. the "needs stamping" case.
_V020_TABLES = {
    "tenants", "users", "load_balancers", "certificates",
    "origin_pools", "sites", "origin_health",
}


def _alembic_cfg(engine: Engine) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent / "alembic"))
    return cfg


def run_migrations(engine: Engine) -> None:
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    has_alembic_version = "alembic_version" in existing_tables
    has_v020_tables = _V020_TABLES.issubset(existing_tables)

    cfg = _alembic_cfg(engine)

    if not has_alembic_version and has_v020_tables:
        # Existing v0.2.0 install — stamp baseline so 0002 applies cleanly
        log.info("alembic_stamp_baseline_for_existing_v020_install")
        command.stamp(cfg, "0001_baseline")
    elif not has_alembic_version and not has_v020_tables:
        # Fresh DB — full upgrade will create everything
        log.info("alembic_fresh_db_full_upgrade")
    else:
        # Already tracked — upgrade is idempotent
        with engine.connect() as conn:
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        log.info("alembic_existing_install", current_revision=current)

    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    log.info("alembic_at_revision", revision=head)
