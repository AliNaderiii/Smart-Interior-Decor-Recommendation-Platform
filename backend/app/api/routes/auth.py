"""Auth: register, login, refresh (rotation), logout (Redis blacklist),
GDPR hard delete.

V2 hardening (see docs/SECURITY_AUDIT_V2.md):
  * A07 — brute-force lockout on /login (5 fails -> 15 min, 429 + Retry-After)
  * A07 — per-IP rate limits on /login (5/min) and /register (3/min)
  * A02 — httpOnly/Secure/SameSite=Strict cookies + double-submit CSRF token
  * A09 — audit_logs written for login/failed login/blocked/logout/register/refresh
"""
from __future__ import annotations

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
    set_auth_cookies,
)
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


def _refresh_token_from(body: RefreshIn | None, request: Request) -> str | None:
    """Accept the refresh token from the body (v1) or the cookie (v2)."""
    if body is not None and body.refresh_token:
        return body.refresh_token
    return request.cookies.get(REFRESH_COOKIE)


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
            db, actions.ACTION_LOGIN_BLOCKED, detail=f"email={email}", request=request
        )
        raise

    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(body.password, user.hashed_password):
        count = brute_force.register_failure(ip, email)
        audit.record(
            db, actions.ACTION_LOGIN_FAILED,
            user_id=user.id if user else None,
            detail=f"email={email} attempt={count}", request=request,
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
    token = _refresh_token_from(body, request)
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
    token = _refresh_token_from(body, request)
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
