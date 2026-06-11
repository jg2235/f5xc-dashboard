"""health_checks

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-11 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "health_checks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("namespace", sa.String(120), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("protocol", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("healthy_threshold", sa.Integer(), nullable=True),
        sa.Column("unhealthy_threshold", sa.Integer(), nullable=True),
        sa.Column("jitter_percent", sa.Integer(), nullable=True),
        sa.Column("http_path", sa.String(2048), nullable=True),
        sa.Column("http_host_header", sa.String(255), nullable=True),
        sa.Column("http_use_http2", sa.Boolean(), nullable=True),
        sa.Column("expected_status_codes", ARRAY(sa.String()), nullable=True),
        sa.Column("raw_spec", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "namespace", "name", name="uq_healthcheck_tenant_ns_name"),
    )
    op.create_index("ix_health_checks_tenant_id", "health_checks", ["tenant_id"])
    op.create_index("ix_health_checks_namespace", "health_checks", ["namespace"])


def downgrade() -> None:
    op.drop_index("ix_health_checks_namespace", table_name="health_checks")
    op.drop_index("ix_health_checks_tenant_id", table_name="health_checks")
    op.drop_table("health_checks")
