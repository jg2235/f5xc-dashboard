"""slice 3 — policies + policy_attachments

Revision ID: 0002_slice3_policies
Revises: 0001_baseline
Create Date: 2026-04-27 14:30:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_slice3_policies"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # app_firewalls
    op.create_table(
        "app_firewalls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("namespace", sa.String(120), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enforcement_mode", sa.String(32), nullable=True),
        sa.Column("default_anonymization", sa.String(64), nullable=True),
        sa.Column("default_bot_setting", sa.String(64), nullable=True),
        sa.Column("detection_settings", sa.String(64), nullable=True),
        sa.Column("enabled_signature_categories", postgresql.ARRAY(sa.String()),
                  nullable=False, server_default="{}"),
        sa.Column("blocked_attack_types", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("custom_rule_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exclusion_rule_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("allowed_response_codes", postgresql.JSONB(), nullable=True),
        sa.Column("raw_spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "namespace", "name", name="uq_appfw_tenant_ns_name"),
    )
    op.create_index("ix_app_firewalls_tenant_id", "app_firewalls", ["tenant_id"])
    op.create_index("ix_app_firewalls_namespace", "app_firewalls", ["namespace"])

    # service_policies
    op.create_table(
        "service_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("namespace", sa.String(120), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_action", sa.String(32), nullable=True),
        sa.Column("rule_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("allow_rule_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deny_rule_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_geo_rules", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_ip_rules", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_path_rules", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("raw_spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "namespace", "name", name="uq_svcpol_tenant_ns_name"),
    )
    op.create_index("ix_service_policies_tenant_id", "service_policies", ["tenant_id"])
    op.create_index("ix_service_policies_namespace", "service_policies", ["namespace"])

    # bot_defense_policies
    op.create_table(
        "bot_defense_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("namespace", sa.String(120), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("protected_endpoint_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("protected_paths", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("has_javascript_challenge", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_captcha_challenge", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_redirect", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_block", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("raw_spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "namespace", "name", name="uq_botpol_tenant_ns_name"),
    )
    op.create_index("ix_bot_defense_policies_tenant_id", "bot_defense_policies", ["tenant_id"])
    op.create_index("ix_bot_defense_policies_namespace", "bot_defense_policies", ["namespace"])

    # api_definitions
    op.create_table(
        "api_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("namespace", sa.String(120), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("spec_format", sa.String(32), nullable=True),
        sa.Column("api_specs_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("endpoint_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_validation_rules", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("raw_spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "namespace", "name", name="uq_apidef_tenant_ns_name"),
    )
    op.create_index("ix_api_definitions_tenant_id", "api_definitions", ["tenant_id"])
    op.create_index("ix_api_definitions_namespace", "api_definitions", ["namespace"])

    # policy_attachments — reverse lookup
    op.create_table(
        "policy_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("policy_type", sa.String(32), nullable=False),
        sa.Column("policy_namespace", sa.String(120), nullable=False),
        sa.Column("policy_name", sa.String(120), nullable=False),
        sa.Column("lb_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("load_balancers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "policy_type", "policy_namespace", "policy_name", "lb_id",
                            name="uq_polatt_full"),
    )
    op.create_index("ix_polatt_tenant_id", "policy_attachments", ["tenant_id"])
    op.create_index("ix_polatt_type", "policy_attachments", ["policy_type"])
    op.create_index("ix_polatt_ns_name", "policy_attachments", ["policy_namespace", "policy_name"])
    op.create_index("ix_polatt_lb_id", "policy_attachments", ["lb_id"])


def downgrade() -> None:
    op.drop_table("policy_attachments")
    op.drop_table("api_definitions")
    op.drop_table("bot_defense_policies")
    op.drop_table("service_policies")
    op.drop_table("app_firewalls")
