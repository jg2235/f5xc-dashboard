"""Alembic migration environment.

Reads DATABASE_URL from app.config (which itself loads .env / container env),
so the same connection string powers app + migrations.
"""
from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app import models  # noqa: F401  -- ensure all models register on Base.metadata
from app.config import get_settings
from app.db import Base

config = context.config

# NOTE: deliberately skipping fileConfig(config.config_file_name).
# alembic.ini's [logger_root] section hijacks the root logger's handlers to
# point at "console", which detaches the structlog handler chain set up by
# app.logging_config.configure_logging() at process startup. As a result,
# any log line emitted via our structured logger AFTER alembic runs (probe
# outcome, f5xc_dashboard_startup, etc.) silently vanishes from docker logs.
# Skipping fileConfig leaves stdlib logging in the state our app configured,
# and alembic's own info-level lines still print through that chain.

# Override sqlalchemy.url from app settings
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
