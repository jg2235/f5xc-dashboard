"""drop tenant token ciphertext (v0.9.0 was wrong-shape; multi-namespace pivot)

Revision ID: 0010_drop_tenant_token_ciphertext
Revises: 0009_tenant_token_ciphertext
Create Date: 2026-05-06 02:57:17.299128
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0010_drop_token_ciphertext'
down_revision: str | None = '0009_tenant_token_ciphertext'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # v0.9.0 was originally scoped as multi-tenant. Phase 1 added an
    # encrypted-at-rest column for per-tenant F5 XC API tokens. The actual
    # need turned out to be multi-NAMESPACE within a single tenant — one
    # token, multiple namespaces. The encryption column adds nothing for
    # that use case (one token lives in env / Docker secret as before).
    # Drop it.
    op.drop_column('tenants', 'f5xc_api_token_ciphertext')


def downgrade() -> None:
    op.add_column(
        'tenants',
        sa.Column('f5xc_api_token_ciphertext', sa.LargeBinary(), nullable=True),
    )
