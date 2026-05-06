"""Authentication endpoints — cookie-based, with rate limiting and audit log.

Flow:
  POST /api/v1/auth/login
    Body: form-urlencoded { username, password }
    Sets: f5xc_session (httpOnly), f5xc_refresh (httpOnly, path=/api/v1/auth),
          f5xc_csrf (NON-httpOnly, readable by SPA)
    Returns: 200 with { user: {...} } body. NO token in response.

  POST /api/v1/auth/refresh
    Reads f5xc_refresh cookie. Issues a new access token + new refresh token
    (rotation) + new CSRF token. Old refresh token's jti is conceptually
    replaced (revocation list not yet implemented; future improvement).

  POST /api/v1/auth/logout
    Clears all three cookies. Audit-logged.

  GET /api/v1/auth/me
    Reads session cookie, returns current user. SPA's first call after page load.

Rate limiting (slowapi) applied to /login: 5/15min per IP.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.auth.audit import record_audit
from app.auth.cookies import (
    clear_auth_cookies,
    set_csrf_cookie,
    set_refresh_cookie,
    set_session_cookie,
)
from app.auth.dependencies import csrf_protect, get_current_user
from app.auth.providers import get_auth_provider
from app.auth.revocation import revoke_jti
from app.auth.security import (
    decode_access_token,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    generate_csrf_token,
)
from app.config import get_settings
from app.db import get_db
from app.models import User
from app.schemas.auth import LoginResponse, UserOut

# Rate limiter — keyed by client IP. Used as a route dependency below.
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


def _safe_revoke(jti: str | None, exp: int | None, *, context: str) -> None:
    """Revoke a jti without breaking the calling flow if Redis is down.

    On the auth-write path (logout, refresh rotation), Redis being
    unavailable is non-fatal: the user's cookies still get cleared
    (logout) or new tokens still issued (refresh). The token's natural
    TTL is the fallback security boundary. Log the failure so ops can
    notice. The READ path (dependencies.get_current_user) is fail-closed
    by design — different policy.
    """
    if not jti or not exp:
        return
    try:
        revoke_jti(jti, exp)
    except Exception as e:  # noqa: BLE001 — Redis errors and others
        from app.logging_config import get_logger
        get_logger(__name__).warning(
            "jwt_revocation_write_failed",
            context=context,
            error=str(e),
        )


def _issue_session(response: Response, user: User) -> None:
    """Set all three cookies for an authenticated session."""
    settings = get_settings()
    access, access_ttl = create_access_token(
        subject=str(user.id),
        extra={"role": user.role, "tenant_id": str(user.tenant_id)},
    )
    refresh, refresh_ttl = create_refresh_token(subject=str(user.id))
    csrf = generate_csrf_token()

    set_session_cookie(response, access, access_ttl)
    set_refresh_cookie(response, refresh, refresh_ttl)
    # CSRF cookie lifetime matches refresh — same session window.
    set_csrf_cookie(response, csrf, refresh_ttl)
    _ = settings  # for forward-compat if we add cookie attrs that depend on settings here


# Rate limit string is read once at import time. Changing the limit
# requires a process restart, which matches Settings/lru_cache semantics.
_LOGIN_RATE_LIMIT = get_settings().auth_login_rate_limit


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in (sets httpOnly cookies)",
)
@limiter.limit(_LOGIN_RATE_LIMIT)
def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> LoginResponse:
    """Per-IP rate-limited via slowapi (`auth_login_rate_limit`, default
    5/15minutes). The 429 response is produced by the slowapi exception
    handler registered in main.py before this handler runs."""
    provider = get_auth_provider()
    user = provider.authenticate(db, form.username, form.password)
    if user is None:
        # Audit before raising — capture the failed username for IR.
        record_audit(
            db,
            event_type="auth.login.failure",
            result="failure",
            request=request,
            actor_username=form.username,
            target=form.username,
        )
        # Generic message — don't disclose whether the user exists.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    _issue_session(response, user)
    record_audit(
        db,
        event_type="auth.login.success",
        result="success",
        request=request,
        actor_user_id=user.id,
        actor_username=user.username,
        tenant_id=user.tenant_id,
    )
    return LoginResponse(user=UserOut.model_validate(user))


@router.post(
    "/refresh",
    response_model=LoginResponse,
    summary="Rotate session via refresh cookie",
    dependencies=[Depends(csrf_protect)],
)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    settings = get_settings()
    refresh_cookie = request.cookies.get(settings.refresh_cookie_name)
    if not refresh_cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token"
        )
    payload = decode_refresh_token(refresh_cookie)
    if not payload or "sub" not in payload:
        # Audit invalid refresh attempt.
        record_audit(
            db, event_type="auth.refresh", result="failure",
            request=request, target="invalid_token",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    import uuid
    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token"
        ) from e
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or disabled"
        )
    # v0.8.0 — revoke the OLD refresh token's jti so it can't be replayed.
    # If Redis is unreachable, log and continue (the user gets new tokens
    # regardless; old refresh expires naturally at its TTL).
    _safe_revoke(payload.get("jti"), payload.get("exp"), context="refresh_rotation")

    # Rotate both tokens + CSRF.
    _issue_session(response, user)
    record_audit(
        db, event_type="auth.refresh", result="success",
        request=request, actor_user_id=user.id, actor_username=user.username,
        tenant_id=user.tenant_id,
    )
    return LoginResponse(user=UserOut.model_validate(user))


@router.post(
    "/logout",
    summary="Clear session cookies",
    dependencies=[Depends(csrf_protect)],
)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """Logout is permissive — even if the session is already invalid, we
    still clear cookies. Audit only if a valid user was attached."""
    user: User | None = None
    try:
        user = get_current_user(request=request, db=db)  # type: ignore[arg-type]
    except HTTPException:
        pass

    # v0.8.0 — revoke both tokens before clearing cookies. Decode-only
    # (we don't care if the access token is structurally valid for
    # revocation purposes; we just want jti+exp to write to the blocklist).
    settings = get_settings()
    access_cookie = request.cookies.get(settings.session_cookie_name)
    if access_cookie:
        access_payload = decode_access_token(access_cookie)
        if access_payload:
            _safe_revoke(
                access_payload.get("jti"),
                access_payload.get("exp"),
                context="logout_access",
            )
    refresh_cookie = request.cookies.get(settings.refresh_cookie_name)
    if refresh_cookie:
        refresh_payload = decode_refresh_token(refresh_cookie)
        if refresh_payload:
            _safe_revoke(
                refresh_payload.get("jti"),
                refresh_payload.get("exp"),
                context="logout_refresh",
            )

    clear_auth_cookies(response)
    if user is not None:
        record_audit(
            db, event_type="auth.logout", result="success", request=request,
            actor_user_id=user.id, actor_username=user.username,
            tenant_id=user.tenant_id,
        )
    return {"status": "ok"}


@router.get("/me", response_model=UserOut, summary="Current user")
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
