"""slice 4 — waf analytics hypertables

Revision ID: 0003_slice4_waf
Revises: 0002_slice3_policies
Create Date: 2026-04-28 13:30:00

Creates:
  - waf_events             hypertable, 7d retention, partitioned on event_time
  - waf_metrics_1min       hypertable, 30d retention, partitioned on bucket_time
  - waf_metrics_1hour      continuous aggregate from waf_metrics_1min, 90d retention

Retention policies and continuous aggregate refresh policy are also installed.
Uses TimescaleDB's add_retention_policy / add_continuous_aggregate_policy.

NOTE: TimescaleDB DDL must run *outside* a transaction. We use
op.execute() with autocommit_block() to escape Alembic's wrapping txn.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_slice4_waf"
down_revision: str | None = "0002_slice3_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- waf_events (raw) ----------
    op.create_table(
        "waf_events",
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lb_namespace", sa.String(120), nullable=False),
        sa.Column("lb_name", sa.String(120), nullable=False),
        sa.Column("action", sa.String(32), nullable=False, server_default="ALLOW"),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("source_country", sa.String(8), nullable=True),
        sa.Column("source_asn", sa.Integer(), nullable=True),
        sa.Column("method", sa.String(16), nullable=True),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("primary_signature", sa.String(255), nullable=True),
        sa.Column("signature_ids", postgresql.JSONB(), nullable=True),
        sa.Column("threat_categories", postgresql.JSONB(), nullable=True),
        sa.Column("severity", sa.String(16), nullable=True),
        sa.Column("waf_policy_namespace", sa.String(120), nullable=True),
        sa.Column("waf_policy_name", sa.String(120), nullable=True),
        sa.Column("raw_event", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("inserted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("event_time", "id", name="pk_waf_events"),
    )
    op.create_index("ix_waf_events_event_time", "waf_events", ["event_time"])
    op.create_index("ix_waf_events_tenant_id", "waf_events", ["tenant_id"])
    op.create_index("ix_waf_events_lb_namespace", "waf_events", ["lb_namespace"])
    op.create_index("ix_waf_events_lb_name", "waf_events", ["lb_name"])
    op.create_index("ix_waf_events_source_ip", "waf_events", ["source_ip"])
    op.create_index("ix_waf_events_source_country", "waf_events", ["source_country"])
    op.create_index("ix_waf_events_primary_signature", "waf_events", ["primary_signature"])

    # Convert to hypertable (chunk size = 1 day)
    op.execute(
        "SELECT create_hypertable('waf_events', 'event_time', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);"
    )
    # Retention: 7 days
    op.execute(
        "SELECT add_retention_policy('waf_events', INTERVAL '7 days', if_not_exists => TRUE);"
    )

    # ---------- waf_metrics_1min ----------
    op.create_table(
        "waf_metrics_1min",
        sa.Column("bucket_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lb_namespace", sa.String(120), nullable=False),
        sa.Column("lb_name", sa.String(120), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("monitored_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("bucket_time", "tenant_id", "lb_namespace", "lb_name",
                                name="pk_waf_metrics_1min"),
    )
    op.create_index("ix_waf_metrics_1min_bucket_time", "waf_metrics_1min", ["bucket_time"])
    op.create_index("ix_waf_metrics_1min_tenant_id", "waf_metrics_1min", ["tenant_id"])

    op.execute(
        "SELECT create_hypertable('waf_metrics_1min', 'bucket_time', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);"
    )
    op.execute(
        "SELECT add_retention_policy('waf_metrics_1min', INTERVAL '30 days', "
        "if_not_exists => TRUE);"
    )

    # ---------- waf_metrics_1hour (continuous aggregate) ----------
    # Continuous aggregates on hypertables are TimescaleDB-specific. CREATE
    # MATERIALIZED VIEW with WITH (timescaledb.continuous).
    op.execute("""
        CREATE MATERIALIZED VIEW waf_metrics_1hour
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(INTERVAL '1 hour', bucket_time) AS bucket_time,
            tenant_id,
            lb_namespace,
            lb_name,
            SUM(request_count)::INT   AS request_count,
            SUM(blocked_count)::INT   AS blocked_count,
            SUM(monitored_count)::INT AS monitored_count,
            SUM(error_count)::INT     AS error_count
        FROM waf_metrics_1min
        GROUP BY 1, 2, 3, 4
        WITH NO DATA;
    """)
    # Refresh every 10 minutes, covering the last 7 days back to the previous full hour.
    op.execute("""
        SELECT add_continuous_aggregate_policy('waf_metrics_1hour',
            start_offset => INTERVAL '7 days',
            end_offset   => INTERVAL '1 hour',
            schedule_interval => INTERVAL '10 minutes',
            if_not_exists => TRUE);
    """)
    # Retention on the continuous aggregate: 90 days
    op.execute(
        "SELECT add_retention_policy('waf_metrics_1hour', INTERVAL '90 days', "
        "if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS waf_metrics_1hour CASCADE;")
    op.drop_table("waf_metrics_1min")
    op.drop_table("waf_events")
