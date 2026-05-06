"""slice 7.2 — security hardening — audit events table

Revision ID: 0007_audit_events
Revises: 0006_slice7_security
Create Date: 2026-04-30 16:00:00

Creates:
  - audit_events  standard table — security audit log

Records security-relevant actions: login attempts, logout, sync triggers,
alert state changes. Cleanup task enforces AUDIT_RETENTION_DAYS retention
(default 180).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_audit_events"
down_revision: str | None = "0006_slice7_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_username", sa.String(120), nullable=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("target", sa.String(255), nullable=True),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("request_ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_events_event_type", "audit_events", ["event_type"], unique=False
    )
    op.create_index(
        "ix_audit_events_created_at", "audit_events", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_table("audit_events")
