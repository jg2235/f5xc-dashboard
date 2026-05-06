"""tenant_namespaces

Revision ID: 0011_tenant_namespaces
Revises: 0010_drop_token_ciphertext
Create Date: 2026-05-06 03:08:17.469019
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011_tenant_namespaces'
down_revision: Union[str, None] = '0010_drop_token_ciphertext'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # v0.9.0 — add `namespaces: ARRAY(String)` for multi-namespace support.
    # The dashboard authenticates against ONE F5 XC tenant with ONE token,
    # but watches MULTIPLE namespaces within that tenant. Existing
    # `f5xc_namespace` column stays as a fallback during migration window
    # (Tenant.effective_namespaces returns this array if populated, else
    # [f5xc_namespace]). Old column dropped in a future revision.
    op.add_column(
        'tenants',
        sa.Column(
            'namespaces',
            sa.ARRAY(sa.String(length=120)),
            nullable=True,
        ),
    )

    # Data migration: populate existing tenants with ["shared", <f5xc_namespace>].
    # The "shared" namespace was historically hardcoded into sync_certificates
    # and sync_policies. Including it in the array preserves behavior on
    # upgrade — the post-v0.9.0 versions of those tasks iterate
    # tenant.effective_namespaces directly, no more shared-as-special-case.
    op.execute("""
        UPDATE tenants
        SET namespaces = ARRAY['shared', f5xc_namespace]::varchar[]
        WHERE namespaces IS NULL AND f5xc_namespace IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_column('tenants', 'namespaces')
