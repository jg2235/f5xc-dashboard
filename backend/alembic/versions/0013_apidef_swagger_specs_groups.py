"""apidef_swagger_specs_groups

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-10 19:45:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_definitions",
        sa.Column(
            "swagger_spec_files",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "api_definitions",
        sa.Column(
            "api_groups",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "api_definitions",
        sa.Column("schema_update_strategy", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_definitions", "schema_update_strategy")
    op.drop_column("api_definitions", "api_groups")
    op.drop_column("api_definitions", "swagger_spec_files")
