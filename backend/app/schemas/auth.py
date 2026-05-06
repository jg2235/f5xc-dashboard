"""Pydantic schemas for the auth API.

Notes
-----
The login/refresh responses intentionally do NOT carry a token. Tokens
travel as httpOnly cookies; the body only confirms identity to the SPA.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    """User shape exposed to the SPA. No password hash, no internal flags."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    role: str
    tenant_id: uuid.UUID | None
    is_active: bool
    created_at: datetime | None = None


class LoginResponse(BaseModel):
    """Body returned by /login and /refresh. Cookies carry the credentials."""

    user: UserOut
