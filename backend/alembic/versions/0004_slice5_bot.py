"""slice 5 — bot analytics hypertables

Revision ID: 0004_slice5_bot
Revises: 0003_slice4_waf
Create Date: 2026-04-29 14:00:00

Creates:
  - bot_events             hypertable, 7d retention, partitioned on event_time
  - bot_metrics_1min       hypertable, 30d retention, partitioned on bucket_time
  - bot_metrics_1hour      continuous aggregate from bot_metrics_1min, 90d retention

Mirrors the slice 4 WAF migration pattern. Retention policies and continuous
aggregate refresh policy are also installed.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_slice5_bot"
down_revision: str | None = "0003_slice4_waf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- bot_events ----------
    op.create_table(
        "bot_events",
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lb_namespace", sa.String(120), nullable=False),
        sa.Column("lb_name", sa.String(120), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="standard"),
        sa.Column("action", sa.String(16), nullable=False, server_default="ALLOW"),
        sa.Column("bot_category", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("confidence_bucket", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("challenge_result", sa.String(16), nullable=False, server_default="not_issued"),
        sa.Column("challenge_type", sa.String(32), nullable=True),
        sa.Column("device_anomalies", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("source_country", sa.String(8), nullable=True),
        sa.Column("source_asn", sa.Integer(), nullable=True),
        sa.Column("method", sa.String(16), nullable=True),
        sa.Column("endpoint_path", sa.String(2048), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ua_family", sa.String(64), nullable=True),
        sa.Column("bot_policy_namespace", sa.String(120), nullable=True),
        sa.Column("bot_policy_name", sa.String(120), nullable=True),
        sa.Column("raw_event", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("inserted_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("event_time", "id", name="pk_bot_events"),
    )
    op.create_index("ix_bot_events_event_time", "bot_events", ["event_time"])
    op.create_index("ix_bot_events_tenant_id", "bot_events", ["tenant_id"])
    op.create_index("ix_bot_events_lb_namespace", "bot_events", ["lb_namespace"])
    op.create_index("ix_bot_events_lb_name", "bot_events", ["lb_name"])
    op.create_index("ix_bot_events_source", "bot_events", ["source"])
    op.create_index("ix_bot_events_action", "bot_events", ["action"])
    op.create_index("ix_bot_events_bot_category", "bot_events", ["bot_category"])
    op.create_index("ix_bot_events_source_ip", "bot_events", ["source_ip"])
    op.create_index("ix_bot_events_source_country", "bot_events", ["source_country"])
    op.create_index("ix_bot_events_endpoint_path", "bot_events", ["endpoint_path"])
    op.create_index("ix_bot_events_ua_family", "bot_events", ["ua_family"])

    op.execute(
        "SELECT create_hypertable('bot_events', 'event_time', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);"
    )
    op.execute(
        "SELECT add_retention_policy('bot_events', INTERVAL '7 days', "
        "if_not_exists => TRUE);"
    )

    # ---------- bot_metrics_1min ----------
    op.create_table(
        "bot_metrics_1min",
        sa.Column("bucket_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lb_namespace", sa.String(120), nullable=False),
        sa.Column("lb_name", sa.String(120), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("challenge_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("block_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("allow_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("bucket_time", "tenant_id", "lb_namespace", "lb_name",
                                name="pk_bot_metrics_1min"),
    )
    op.create_index("ix_bot_metrics_1min_bucket_time", "bot_metrics_1min", ["bucket_time"])
    op.create_index("ix_bot_metrics_1min_tenant_id", "bot_metrics_1min", ["tenant_id"])

    op.execute(
        "SELECT create_hypertable('bot_metrics_1min', 'bucket_time', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);"
    )
    op.execute(
        "SELECT add_retention_policy('bot_metrics_1min', INTERVAL '30 days', "
        "if_not_exists => TRUE);"
    )

    # ---------- bot_metrics_1hour (continuous aggregate) ----------
    op.execute("""
        CREATE MATERIALIZED VIEW bot_metrics_1hour
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(INTERVAL '1 hour', bucket_time) AS bucket_time,
            tenant_id,
            lb_namespace,
            lb_name,
            SUM(request_count)::INT   AS request_count,
            SUM(challenge_count)::INT AS challenge_count,
            SUM(block_count)::INT     AS block_count,
            SUM(allow_count)::INT     AS allow_count
        FROM bot_metrics_1min
        GROUP BY 1, 2, 3, 4
        WITH NO DATA;
    """)
    op.execute("""
        SELECT add_continuous_aggregate_policy('bot_metrics_1hour',
            start_offset => INTERVAL '7 days',
            end_offset   => INTERVAL '1 hour',
            schedule_interval => INTERVAL '10 minutes',
            if_not_exists => TRUE);
    """)
    op.execute(
        "SELECT add_retention_policy('bot_metrics_1hour', INTERVAL '90 days', "
        "if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS bot_metrics_1hour CASCADE;")
    op.drop_table("bot_metrics_1min")
    op.drop_table("bot_events")
