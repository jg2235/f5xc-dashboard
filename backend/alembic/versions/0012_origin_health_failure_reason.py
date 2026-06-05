"""origin_health_failure_reason

Revision ID: 0012_origin_health_failure_reason
Revises: 0011_tenant_namespaces
Create Date: 2026-06-05 19:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011_tenant_namespaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "origin_health",
        sa.Column("failure_reason", sa.String(120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("origin_health", "failure_reason")
