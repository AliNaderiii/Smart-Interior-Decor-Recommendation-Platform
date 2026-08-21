"""Auth: register, login, refresh (rotation), logout (Redis blacklist),
GDPR hard delete.

V2 hardening (see docs/SECURITY_AUDIT_V2.md):
  * A07 — brute-force lockout on /login (5 fails -> 15 min, 429 + Retry-After)
  * A07 — per-IP rate limits on /login (5/min) and /register (3/min)
  * A02 — httpOnly/Secure/SameSite=Strict cookies + double-submit CSRF token
  * A09 — audit_logs written for login/failed login/blocked/logout/register/refresh

Stage 03 hardening (see docs/security/THREAT_MODEL.md):
  * T-03 — constant-work login: a miss now performs a dummy bcrypt verify, so
    response time no longer discloses whether an address is registered
  * T-09 — /refresh and /logout enforce the double-submit CSRF token for
    cookie sessions instead of relying on SameSite alone
  * T-10 — registration passwords are bounded at bcrypt's real 72-byte input
  * T-38 — audit `detail` stores a keyed pseudonym, not the raw address
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core import brute_force
from app.core.config import settings
from app.core.cookies import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    require_csrf_for_cookie_session,
    set_auth_cookies,
)
from app.core.log_redaction import pseudonymise_email
from app.core.rate_limit import enforce_rate_limit
from app.core.redis_client import get_redis
from app.core.security import (
    JWTError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models import audit_log as actions
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn
from app.schemas.common import ok
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: User) -> dict:
    sub = user.subscription
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "subscription_active": bool(sub and sub.is_active),
        "subscription_plan": sub.plan if sub else "free",
    }


def _token_pair(user_id: str) -> dict:
    return {
        "access_token": create_token(user_id, "access"),
        "refresh_token": create_token(user_id, "refresh"),
        "token_type": "bearer",
    }


def _issue(response: Response, user_id: str) -> dict:
    """Create a token pair and, when enabled, mirror it into httpOnly cookies."""
    pair = _token_pair(user_id)
    if settings.USE_COOKIE_AUTH:
        csrf = set_auth_cookies(response, pair["access_token"], pair["refresh_token"])
        pair["csrf_token"] = csrf
    return pair


#: A bcrypt hash of a value nobody knows, used only to burn the same CPU on a
#: login miss as on a hit (T-03). Computed lazily and once: hashing at import
#: time would add ~250 ms to every process start, including the test suite.
_DUMMY_HASH: str | None = None


def _equalise_login_work(password: str) -> None:
    """Spend the same time on a missing account as on an existing one.

    Baseline measurement (probe T-01): an existing account took 268 ms (bcrypt)
    and a non-existent one 9 ms, because `verify_password` was skipped
    entirely. A 30x gap is a reliable, remotely observable oracle for "is this
    address registered?" — which turns a credential-stuffing list into a
    validated target list, and leaks membership of a service users may not want
    to be known to use.
    """
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(24))
    verify_password(password, _DUMMY_HASH)


def _refresh_token_from(
    body: RefreshIn | None, request: Request
) -> tuple[str | None, bool]:
    """Accept the refresh token from the body (v1) or the cookie (v2).

    Returns ``(token, came_from_cookie)``. The flag matters: a token supplied in
    the request body is *not* ambient authority — a cross-site attacker cannot
    read it, so replaying it is not CSRF. Only the cookie path needs the
    double-submit check, and requiring it for Bearer/CLI callers would break
    them for no security gain.
    """
    if body is not None and body.refresh_token:
        return body.refresh_token, False
    return request.cookies.get(REFRESH_COOKIE), True


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip = audit.client_ip(request)
    # A07: stop scripted account flooding (Phase 0B: 5/5 registrations succeeded).
    enforce_rate_limit(f"register:{ip}", limit=settings.REGISTER_RATE_LIMIT_PER_MINUTE)

    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    user.subscription = Subscription(plan="free", is_active=False)
    db.add(user)
    db.commit()
    audit.record(
        db, actions.ACTION_REGISTER, user_id=user.id,
        detail=f"role={user.role}", request=request,
    )
    return ok({"user": _user_out(user), **_issue(response, user.id)})


@router.post("/login")
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip = audit.client_ip(request)
    email = body.email.lower()

    # A07 #1: per-IP request rate limit (cheap, blocks floods).
    enforce_rate_limit(f"login:{ip}", limit=settings.LOGIN_RATE_LIMIT_PER_MINUTE)
    # A07 #2: per ip+email lockout (blocks slow, targeted guessing).
    try:
        brute_force.check_not_blocked(ip, email)
    except HTTPException:
        audit.record(
            db, actions.ACTION_LOGIN_BLOCKED,
            detail=f"account={pseudonymise_email(email)}", request=request,
        )
        raise

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        # T-03: burn the bcrypt cost the hit path would have spent.
        _equalise_login_work(body.password)
        password_ok = False
    else:
        password_ok = verify_password(body.password, user.hashed_password)
    if not password_ok:
        count = brute_force.register_failure(ip, email)
        audit.record(
            db, actions.ACTION_LOGIN_FAILED,
            user_id=user.id if user else None,
            detail=f"account={pseudonymise_email(email)} attempt={count}",
            request=request,
        )
        # Re-check so the *5th* failure itself is answered with the lockout.
        brute_force.check_not_blocked(ip, email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if not user.is_active:
        audit.record(
            db, actions.ACTION_LOGIN_FAILED, user_id=user.id,
            detail="account disabled", request=request,
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    brute_force.reset(ip, email)
    audit.record(db, actions.ACTION_LOGIN, user_id=user.id, request=request)
    return ok({"user": _user_out(user), **_issue(response, user.id)})


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    body: RefreshIn | None = None,
    db: Session = Depends(get_db),
):
    token, from_cookie = _refresh_token_from(body, request)
    if from_cookie:
        # T-09: /refresh mints a fresh credential pair, so it is the
        # highest-value CSRF target in the API and must not rely on SameSite
        # alone when the credential travels as an ambient cookie.
        require_csrf_for_cookie_session(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing refresh token")
    try:
        payload = decode_token(token, expected_type="refresh")
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    redis = get_redis()
    if redis.get(f"blacklist:{payload['jti']}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token revoked")
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    # Rotate: blacklist the used refresh token for its remaining lifetime.
    redis.setex(
        f"blacklist:{payload['jti']}",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "1",
    )
    audit.record(db, actions.ACTION_TOKEN_REFRESH, user_id=user.id, request=request)
    return ok(_issue(response, user.id))


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    body: RefreshIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token, from_cookie = _refresh_token_from(body, request)
    if from_cookie:
        require_csrf_for_cookie_session(request)
    if token:
        try:
            payload = decode_token(token, expected_type="refresh")
            get_redis().setex(
                f"blacklist:{payload['jti']}",
                timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
                "1",
            )
        except JWTError:
            pass  # already invalid — logout is idempotent
    clear_auth_cookies(response)
    audit.record(db, actions.ACTION_LOGOUT, user_id=user.id, request=request)
    return ok({"message": "Logged out"})


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return ok(_user_out(user))
