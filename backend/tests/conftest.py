"""Test fixtures. The ORM uses Postgres-only types (ARRAY, JSONB, UUID),
so DB-level tests run against the compose Postgres when needed.
Pure-function tests (transformers, cert parsing) run without a DB."""
from __future__ import annotations

import os

os.environ.setdefault("F5XC_MOCK", "true")
os.environ.setdefault("F5XC_API_TOKEN", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
