"""slice 6 — API statistics + ML discovery

Revision ID: 0005_slice6_api
Revises: 0004_slice5_bot
Create Date: 2026-04-29 18:00:00

Creates:
  - api_endpoints           standard table (bounded cardinality)
  - api_discovery_states    standard table (one row per LB)
  - api_metrics_1min        hypertable, 30d retention
  - api_metrics_1hour       continuous aggregate, 90d retention

Latency percentiles can't be averaged across buckets correctly without
preserving the underlying distribution. The 1-hour rollup uses MAX(p95)
and MAX(p99) for the worst-case-in-hour pattern, and AVG(p50) for typical.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_slice6_api"
down_revision: str | None = "0004_slice5_bot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add declared_endpoints column to existing api_definitions for shadow detection
    op.add_column(
        "api_definitions",
        sa.Column("declared_endpoints", postgresql.JSONB(), nullable=True),
    )

    # ---------- api_endpoints ----------
    op.create_table(
        "api_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lb_namespace", sa.String(120), nullable=False),
        sa.Column("lb_name", sa.String(120), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("endpoint_path", sa.String(2048), nullable=False),
        sa.Column("is_shadow", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("api_definition_namespace", sa.String(120), nullable=True),
        sa.Column("api_definition_name", sa.String(120), nullable=True),
        sa.Column("discovery_confidence", sa.Integer(), nullable=True),
        sa.Column("total_request_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_codes", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("query_params", postgresql.JSONB(), nullable=True),
        sa.Column("body_params", postgresql.JSONB(), nullable=True),
        sa.Column("auth_type", sa.String(16), nullable=True),
        sa.Column("inserted_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_api_endpoints"),
        sa.UniqueConstraint("tenant_id", "lb_namespace", "lb_name", "method", "endpoint_path",
                            name="uq_api_endpoint_identity"),
    )
    op.create_index("ix_api_endpoints_tenant_id", "api_endpoints", ["tenant_id"])
    op.create_index("ix_api_endpoints_lb_namespace", "api_endpoints", ["lb_namespace"])
    op.create_index("ix_api_endpoints_lb_name", "api_endpoints", ["lb_name"])
    op.create_index("ix_api_endpoints_is_shadow", "api_endpoints", ["is_shadow"])
    op.create_index("ix_api_endpoints_auth_type", "api_endpoints", ["auth_type"])

    # ---------- api_discovery_states ----------
    op.create_table(
        "api_discovery_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lb_namespace", sa.String(120), nullable=False),
        sa.Column("lb_name", sa.String(120), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("total_endpoints_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_traffic_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_learning_update", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inserted_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_api_discovery_states"),
        sa.UniqueConstraint("tenant_id", "lb_namespace", "lb_name",
                            name="uq_api_discovery_state_lb"),
    )
    op.create_index("ix_api_discovery_states_tenant_id", "api_discovery_states", ["tenant_id"])
    op.create_index("ix_api_discovery_states_lb_name", "api_discovery_states", ["lb_name"])
    op.create_index("ix_api_discovery_states_state", "api_discovery_states", ["state"])

    # ---------- api_metrics_1min ----------
    op.create_table(
        "api_metrics_1min",
        sa.Column("bucket_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lb_namespace", sa.String(120), nullable=False),
        sa.Column("lb_name", sa.String(120), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("endpoint_path", sa.String(2048), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_4xx_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_5xx_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_p50_ms", sa.Float(), nullable=True),
        sa.Column("latency_p95_ms", sa.Float(), nullable=True),
        sa.Column("latency_p99_ms", sa.Float(), nullable=True),
        sa.Column("inserted_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint(
            "bucket_time", "tenant_id", "lb_namespace", "lb_name",
            "method", "endpoint_path",
            name="pk_api_metrics_1min",
        ),
    )
    op.create_index("ix_api_metrics_1min_bucket_time", "api_metrics_1min", ["bucket_time"])
    op.create_index("ix_api_metrics_1min_tenant_id", "api_metrics_1min", ["tenant_id"])

    op.execute(
        "SELECT create_hypertable('api_metrics_1min', 'bucket_time', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);"
    )
    op.execute(
        "SELECT add_retention_policy('api_metrics_1min', INTERVAL '30 days', "
        "if_not_exists => TRUE);"
    )

    # ---------- api_metrics_1hour (continuous aggregate) ----------
    op.execute("""
        CREATE MATERIALIZED VIEW api_metrics_1hour
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(INTERVAL '1 hour', bucket_time) AS bucket_time,
            tenant_id,
            lb_namespace,
            lb_name,
            method,
            endpoint_path,
            SUM(request_count)::INT     AS request_count,
            SUM(error_4xx_count)::INT   AS error_4xx_count,
            SUM(error_5xx_count)::INT   AS error_5xx_count,
            AVG(latency_p50_ms)         AS latency_p50_avg_ms,
            MAX(latency_p95_ms)         AS latency_p95_max_ms,
            MAX(latency_p99_ms)         AS latency_p99_max_ms
        FROM api_metrics_1min
        GROUP BY 1, 2, 3, 4, 5, 6
        WITH NO DATA;
    """)
    op.execute("""
        SELECT add_continuous_aggregate_policy('api_metrics_1hour',
            start_offset => INTERVAL '7 days',
            end_offset   => INTERVAL '1 hour',
            schedule_interval => INTERVAL '10 minutes',
            if_not_exists => TRUE);
    """)
    op.execute(
        "SELECT add_retention_policy('api_metrics_1hour', INTERVAL '90 days', "
        "if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS api_metrics_1hour CASCADE;")
    op.drop_table("api_metrics_1min")
    op.drop_table("api_discovery_states")
    op.drop_table("api_endpoints")
    op.drop_column("api_definitions", "declared_endpoints")
