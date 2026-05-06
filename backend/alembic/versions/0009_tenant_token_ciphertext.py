"""tenant_token_ciphertext

Revision ID: 0be8d410b874
Revises: 0008_tenant_token_nullable
Create Date: 2026-05-05 13:02:59.216801
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0009_tenant_token_ciphertext'
down_revision: str | None = '0008_tenant_token_nullable'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # v0.9.0 — add encrypted-at-rest column for per-tenant F5 XC API tokens.
    # Coexists with the existing plaintext f5xc_api_token column during the
    # migration window. Sync tasks prefer ciphertext if present, fall back
    # to plaintext if NULL, fall back to env (settings.f5xc_api_token) if both NULL.
    # Plaintext column is removed in a future revision once all tenants migrate.
    op.add_column(
        'tenants',
        sa.Column('f5xc_api_token_ciphertext', sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('tenants', 'f5xc_api_token_ciphertext')
