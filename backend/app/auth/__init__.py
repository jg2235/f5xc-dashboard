"""Authentication — pluggable providers."""
from app.auth.dependencies import get_current_user, require_admin
from app.auth.providers import LocalAuthProvider, OIDCAuthProvider, get_auth_provider
from app.auth.security import create_access_token, hash_password, verify_password

__all__ = [
    "LocalAuthProvider",
    "OIDCAuthProvider",
    "create_access_token",
    "get_auth_provider",
    "get_current_user",
    "hash_password",
    "require_admin",
    "verify_password",
]
