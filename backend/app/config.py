"""Centralised configuration.

Production secret handling
--------------------------
Sensitive values (JWT_SECRET_KEY, F5XC_API_TOKEN, POSTGRES_PASSWORD) can be
supplied three ways, in order of precedence:

1. Docker secrets — files at /run/secrets/<lowercase_key>. RECOMMENDED for
   production. The compose `secrets:` block mounts these read-only into the
   backend container; they never appear in the container's environment listing.
2. Environment variables (or .env file). For local development.
3. Defaults baked into Settings — empty/placeholder values that fail closed.

The `_bootstrap_secrets()` helper writes the contents of /run/secrets/<key>
into os.environ before pydantic reads it, so secrets-file values are picked
up transparently by the same Settings field.

Production hardening
--------------------
`Settings.validate_production_safe()` runs from main.py at startup. When
F5XC_MOCK=false (live mode), the app refuses to boot if:
  - JWT_SECRET_KEY is empty, the default placeholder, or under 32 chars
  - F5XC_API_TOKEN is empty
  - SESSION_COOKIE_SECURE is False (cookies must require TLS in prod)

Mock mode (F5XC_MOCK=true) skips these checks for local exploration.
"""
from __future__ import annotations

import os
import secrets as _secrets_lib
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRETS_DIR = Path("/run/secrets")
_SECRETS_BACKED_KEYS = (
    "jwt_secret_key",
    "f5xc_api_token",
    "postgres_password",
)


def _resolve_secret(key: str) -> str | None:
    path = _SECRETS_DIR / key
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
    return None


def _bootstrap_secrets() -> None:
    """Pre-populate os.environ from Docker secrets before pydantic reads it."""
    for key in _SECRETS_BACKED_KEYS:
        upper = key.upper()
        if upper in os.environ and os.environ[upper]:
            continue
        value = _resolve_secret(key)
        if value:
            os.environ[upper] = value


_bootstrap_secrets()


JWT_SECRET_PLACEHOLDER = "dev-insecure-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+psycopg://f5xc:f5xc_dev_password@localhost:5432/f5xc_dashboard"
    )

    # Redis / Celery
    redis_url: str = Field(default="redis://localhost:6379/0")

    # JWT — secret bootstrapped from /run/secrets/jwt_secret_key if mounted.
    jwt_secret_key: str = Field(default=JWT_SECRET_PLACEHOLDER)
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expires_minutes: int = Field(default=15)
    jwt_refresh_token_expires_days: int = Field(default=7)

    # Cookie + CSRF
    session_cookie_name: str = Field(default="f5xc_session")
    refresh_cookie_name: str = Field(default="f5xc_refresh")
    csrf_cookie_name: str = Field(default="f5xc_csrf")
    session_cookie_secure: bool = Field(default=True)
    session_cookie_samesite: Literal["lax", "strict", "none"] = Field(default="strict")
    session_cookie_domain: str = Field(default="")

    # CORS — when frontend & backend share origin (Caddy proxy), leave empty.
    cors_allow_origins: str = Field(default="")

    # Rate limit on /login (slowapi). Format: "<count>/<period>".
    auth_login_rate_limit: str = Field(default="5/15minutes")

    # Auth provider
    auth_provider: Literal["local", "oidc"] = Field(default="local")
    oidc_issuer_url: str = Field(default="")
    oidc_client_id: str = Field(default="")
    oidc_client_secret: str = Field(default="")
    oidc_redirect_uri: str = Field(default="http://localhost:3000/auth/callback")

    # F5 XC
    f5xc_mock: bool = Field(default=True)
    analytics_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices('F5XC_ANALYTICS_ENABLED', 'analytics_enabled'),
        description=(
            'When False, sync tasks that hit /api/data/* analytics endpoints '
            'are skipped. Set False on tenants without analytics module '
            'licensed to eliminate 404 noise. Config-plane syncs are '
            'unaffected.'
        ),
    )
    f5xc_tenant: str = Field(default="example-tenant")
    f5xc_api_token: str = Field(default="")
    f5xc_namespace: str = Field(default="default")
    f5xc_request_timeout_seconds: int = Field(default=30)
    f5xc_max_retries: int = Field(default=5)
    f5xc_api_url_template: str = Field(default="https://{tenant}.console.ves.io")

    # Polling
    poll_config_interval: int = Field(default=600)
    poll_healthcheck_interval: int = Field(default=120)
    poll_analytics_interval: int = Field(default=300)

    # Healthcheck circuit breaker (slice 2)
    healthcheck_max_calls_per_cycle: int = Field(default=500)
    healthcheck_per_request_delay_ms: int = Field(default=100)

    # Cert thresholds
    cert_warn_days: int = Field(default=30)
    cert_critical_days: int = Field(default=7)

    # WAF analytics (slice 4)
    waf_event_window_minutes: int = Field(default=10)
    waf_metrics_window_minutes: int = Field(default=10)
    waf_max_events_per_cycle: int = Field(default=500)
    waf_topk_size: int = Field(default=12)

    # Bot analytics (slice 5)
    bot_event_window_minutes: int = Field(default=10)
    bot_metrics_window_minutes: int = Field(default=10)
    bot_max_events_per_cycle: int = Field(default=500)
    bot_topk_size: int = Field(default=12)

    # API analytics (slice 6)
    api_metrics_window_minutes: int = Field(default=10)
    api_max_endpoints_per_cycle: int = Field(default=2000)
    api_topk_size: int = Field(default=12)

    # Security analytics + alerting (slice 7)
    security_profile_window_minutes: int = Field(default=1440)
    security_max_attackers_per_cycle: int = Field(default=2000)
    security_topk_size: int = Field(default=12)
    alert_retention_days: int = Field(default=90)
    alert_waf_block_burst_threshold: int = Field(default=50)
    alert_bot_cred_stuff_min_events: int = Field(default=20)
    alert_bot_cred_stuff_failure_pct: float = Field(default=50.0)
    alert_api_shadow_emergence_samples: int = Field(default=100)
    alert_cert_expiry_critical_days: int = Field(default=7)
    alert_rule_waf_burst_enabled: bool = Field(default=True)
    alert_rule_waf_new_attacker_enabled: bool = Field(default=True)
    alert_rule_bot_cred_stuff_enabled: bool = Field(default=True)
    alert_rule_api_state_change_enabled: bool = Field(default=True)
    alert_rule_api_shadow_enabled: bool = Field(default=True)
    alert_rule_cert_expiry_enabled: bool = Field(default=True)

    # Audit log retention
    audit_retention_days: int = Field(default=180)

    # Logging
    log_level: str = Field(default="INFO")
    log_format: Literal["json", "console"] = Field(default="json")

    @property
    def f5xc_base_url(self) -> str:
        return self.f5xc_api_url_template.format(tenant=self.f5xc_tenant)

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.cors_allow_origins.strip():
            return []
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    def validate_production_safe(self) -> list[str]:
        """Return list of production-config violations. Empty = OK."""
        problems: list[str] = []
        if self.f5xc_mock:
            return []
        if not self.jwt_secret_key or self.jwt_secret_key == JWT_SECRET_PLACEHOLDER:
            problems.append(
                "JWT_SECRET_KEY is the default placeholder. "
                "Generate one: `python -c 'import secrets; print(secrets.token_urlsafe(48))'` "
                "and write to /run/secrets/jwt_secret_key or set in .env."
            )
        elif len(self.jwt_secret_key) < 32:
            problems.append(
                f"JWT_SECRET_KEY too short ({len(self.jwt_secret_key)} chars). "
                "Minimum 32 chars required for HS256."
            )
        if not self.f5xc_api_token:
            problems.append(
                "F5XC_API_TOKEN is empty. Provide via /run/secrets/f5xc_api_token or .env."
            )
        if not self.session_cookie_secure:
            problems.append(
                "SESSION_COOKIE_SECURE is False. Cookies must be Secure-flagged "
                "in production. Set SESSION_COOKIE_SECURE=true."
            )
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


def generate_jwt_secret() -> str:
    """Generate a fresh 256-bit JWT secret. Convenience for ops scripts."""
    return _secrets_lib.token_urlsafe(48)
