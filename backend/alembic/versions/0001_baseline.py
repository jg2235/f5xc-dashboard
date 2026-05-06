"""baseline v0.2.0 schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-27 14:00:00

This is the v0.2.0 baseline. Existing deployments running v0.2.0 should
be stamped to this revision (`alembic stamp 0001_baseline`) — the migration
is then a no-op for them. Fresh deployments will run the full upgrade.

The startup migration helper (app/migrations.py) detected pre-existing
tables and skipped on fresh DBs, so applying this on a fresh DB is the
correct path forward.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # tenants
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("f5xc_tenant", sa.String(120), nullable=False),
        sa.Column("f5xc_namespace", sa.String(120), nullable=False),
        sa.Column("f5xc_api_token", sa.String(512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("username", sa.String(120), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"])

    # load_balancers
    op.create_table(
        "load_balancers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("namespace", sa.String(120), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("domains", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("lb_type", sa.String(32), nullable=False, server_default="http"),
        sa.Column("advertise_mode", sa.String(64), nullable=True),
        sa.Column("advertised_sites", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("has_waf", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_service_policy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_bot_defense", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_api_protection", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("origin_pool_refs", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("cert_ref", sa.String(255), nullable=True),
        sa.Column("raw_spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "namespace", "name", name="uq_lb_tenant_ns_name"),
    )
    op.create_index("ix_load_balancers_tenant_id", "load_balancers", ["tenant_id"])

    # certificates
    op.create_table(
        "certificates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("namespace", sa.String(120), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("subject", sa.String(512), nullable=True),
        sa.Column("issuer", sa.String(512), nullable=True),
        sa.Column("san_dns", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("serial_number", sa.String(128), nullable=True),
        sa.Column("fingerprint_sha256", sa.String(128), nullable=True),
        sa.Column("auto_cert", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("raw_spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "namespace", "name", name="uq_cert_tenant_ns_name"),
    )
    op.create_index("ix_certificates_tenant_id", "certificates", ["tenant_id"])
    op.create_index("ix_certificates_not_after", "certificates", ["not_after"])

    # origin_pools
    op.create_table(
        "origin_pools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("namespace", sa.String(120), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("lb_algorithm", sa.String(64), nullable=True),
        sa.Column("origin_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("origin_addresses", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("healthcheck_refs", postgresql.JSONB(), nullable=True),
        sa.Column("healthy_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unhealthy_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_healthcheck_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "namespace", "name", name="uq_pool_tenant_ns_name"),
    )
    op.create_index("ix_origin_pools_tenant_id", "origin_pools", ["tenant_id"])

    # sites
    op.create_table(
        "sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("site_type", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("operational_status", sa.String(32), nullable=True),
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("raw_spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_site_tenant_name"),
    )
    op.create_index("ix_sites_tenant_id", "sites", ["tenant_id"])

    # origin_health
    op.create_table(
        "origin_health",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pool_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("origin_pools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("origin_address", sa.String(255), nullable=False),
        sa.Column("origin_port", sa.Integer(), nullable=True),
        sa.Column("site_name", sa.String(120), nullable=False),
        sa.Column("site_type", sa.String(16), nullable=True),
        sa.Column("raw_status", sa.String(32), nullable=False, server_default="UNKNOWN"),
        sa.Column("classified_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_status_change", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("pool_id", "origin_address", "origin_port", "site_name",
                            name="uq_origin_health_pool_origin_site"),
    )
    op.create_index("ix_origin_health_tenant_id", "origin_health", ["tenant_id"])
    op.create_index("ix_origin_health_pool_id", "origin_health", ["pool_id"])
    op.create_index("ix_origin_health_site_name", "origin_health", ["site_name"])


def downgrade() -> None:
    op.drop_table("origin_health")
    op.drop_table("sites")
    op.drop_table("origin_pools")
    op.drop_table("certificates")
    op.drop_table("load_balancers")
    op.drop_table("users")
    op.drop_table("tenants")
