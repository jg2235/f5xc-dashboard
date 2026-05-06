"""slice 7 — security analytics + alerts

Revision ID: 0006_slice7_security
Revises: 0005_slice6_api
Create Date: 2026-04-29 22:00:00

Creates:
  - attacker_profiles  standard table — cross-signal correlator cache
  - alerts             standard table — persistent alert log

No new hypertables. Slice 7 reads from existing waf_events / bot_events /
api_metrics_1min hypertables and writes summarized state.

Alert retention is enforced by application-level cleanup (delete_old_alerts
task), not a TimescaleDB retention policy, since alerts are not in a hypertable.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_slice7_security"
down_revision: str | None = "0005_slice6_api"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- attacker_profiles ----------
    op.create_table(
        "attacker_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_ip", sa.String(64), nullable=False),
        sa.Column("source_asn", sa.Integer(), nullable=True),
        sa.Column("source_country", sa.String(8), nullable=True),
        sa.Column("waf_block_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("waf_monitor_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bot_block_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bot_challenge_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("api_4xx_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("top_endpoint", sa.String(2048), nullable=True),
        sa.Column("top_signature", sa.String(120), nullable=True),
        sa.Column("distinct_lbs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inserted_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_attacker_profiles"),
        sa.UniqueConstraint(
            "tenant_id", "source_ip", "source_asn", "source_country",
            name="uq_attacker_profile_identity",
        ),
    )
    op.create_index("ix_attacker_profiles_tenant_id", "attacker_profiles", ["tenant_id"])
    op.create_index("ix_attacker_profiles_source_ip", "attacker_profiles", ["source_ip"])
    op.create_index("ix_attacker_profiles_source_asn", "attacker_profiles", ["source_asn"])
    op.create_index("ix_attacker_profiles_source_country", "attacker_profiles", ["source_country"])
    op.create_index("ix_attacker_profiles_total_events", "attacker_profiles", ["total_events"])

    # ---------- alerts ----------
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("dedupe_key", sa.String(256), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.String(2048), nullable=False, server_default=""),
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inserted_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_alerts"),
        sa.UniqueConstraint(
            "tenant_id", "rule_id", "dedupe_key",
            name="uq_alert_dedup_identity",
        ),
    )
    op.create_index("ix_alerts_tenant_id", "alerts", ["tenant_id"])
    op.create_index("ix_alerts_rule_id", "alerts", ["rule_id"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_last_seen_at", "alerts", ["last_seen_at"])


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("attacker_profiles")
