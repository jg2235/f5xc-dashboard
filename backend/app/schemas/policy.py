"""Policy schemas (slice 3)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

PolicyType = Literal["app_firewall", "service_policy", "bot_defense_policy", "api_definition"]


class PolicyAttachmentRef(BaseModel):
    """An LB that references a policy."""
    lb_id: uuid.UUID
    lb_name: str
    lb_namespace: str

    model_config = {"from_attributes": True}


class PolicyBase(BaseModel):
    id: uuid.UUID
    namespace: str
    name: str
    is_shared: bool
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class AppFirewallSummary(PolicyBase):
    enforcement_mode: str | None
    enabled_signature_categories: list[str]
    blocked_attack_types: list[str]
    custom_rule_count: int
    exclusion_rule_count: int


class AppFirewallDetail(AppFirewallSummary):
    default_anonymization: str | None
    default_bot_setting: str | None
    detection_settings: str | None
    allowed_response_codes: list[int] | None
    raw_spec: dict[str, Any]
    attached_to: list[PolicyAttachmentRef]


class ServicePolicySummary(PolicyBase):
    default_action: str | None
    rule_count: int
    allow_rule_count: int
    deny_rule_count: int
    has_geo_rules: bool
    has_ip_rules: bool
    has_path_rules: bool


class ServicePolicyDetail(ServicePolicySummary):
    raw_spec: dict[str, Any]
    attached_to: list[PolicyAttachmentRef]


class BotDefensePolicySummary(PolicyBase):
    protected_endpoint_count: int
    has_javascript_challenge: bool
    has_captcha_challenge: bool
    has_redirect: bool
    has_block: bool


class BotDefensePolicyDetail(BotDefensePolicySummary):
    protected_paths: list[str]
    raw_spec: dict[str, Any]
    attached_to: list[PolicyAttachmentRef]


class ApiDefinitionSummary(PolicyBase):
    spec_format: str | None
    api_specs_count: int
    endpoint_count: int
    has_validation_rules: bool


class ApiDefinitionDetail(ApiDefinitionSummary):
    raw_spec: dict[str, Any]
    attached_to: list[PolicyAttachmentRef]


class PolicyTypeStats(BaseModel):
    total: int
    shared: int
    local: int
    unattached: int


class PolicyStats(BaseModel):
    """Aggregate stats across all 4 policy types."""
    app_firewall: PolicyTypeStats
    service_policy: PolicyTypeStats
    bot_defense_policy: PolicyTypeStats
    api_definition: PolicyTypeStats
