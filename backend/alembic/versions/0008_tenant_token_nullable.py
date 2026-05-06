"""tenant token nullable - v0.8.0 step 2

Revision ID: 0008_tenant_token_nullable
Revises: 0007_audit_events
Create Date: 2026-05-02

Drop NOT NULL on tenants.f5xc_api_token. Step 8 of v0.7.2 made the env-side
token (via Docker secrets at /run/secrets/f5xc_api_token) the authoritative
source for single-tenant deployments. The per-tenant column is now optional;
it remains for future multi-tenant deployments where each tenant has its
own credentials.

Also drops the empty-string default — NULL is the correct "no per-tenant
override" sentinel; empty string conflated "explicitly no token" with
"never set."
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0008_tenant_token_nullable"
down_revision = "0007_audit_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the NOT NULL + default first so the subsequent UPDATE can write NULL.
    # (The original order — UPDATE then ALTER — fails because the column still
    # forbids NULL when the UPDATE runs.)
    op.alter_column(
        "tenants",
        "f5xc_api_token",
        existing_type=sa.String(length=512),
        nullable=True,
        server_default=None,
    )
    # Now convert existing empty strings to NULL so the new "no-override"
    # semantic is consistent across old and new rows.
    op.execute(
        "UPDATE tenants SET f5xc_api_token = NULL WHERE f5xc_api_token = ''"
    )


def downgrade() -> None:
    # Revert: replace NULLs with empty string, then re-apply NOT NULL + default.
    op.execute(
        "UPDATE tenants SET f5xc_api_token = '' WHERE f5xc_api_token IS NULL"
    )
    op.alter_column(
        "tenants",
        "f5xc_api_token",
        existing_type=sa.String(length=512),
        nullable=False,
        server_default="",
    )
