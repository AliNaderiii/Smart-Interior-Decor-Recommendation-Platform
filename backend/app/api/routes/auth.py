"""Auth: register, login, refresh (rotation), logout (Redis blacklist),
GDPR hard delete."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.redis_client import get_redis
from app.core.security import (
    JWTError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn
from app.schemas.common import ok

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


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)):
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
    return ok({"user": _user_out(user), **_token_pair(user.id)})


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    return ok({"user": _user_out(user), **_token_pair(user.id)})


@router.post("/refresh")
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
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
    return ok(_token_pair(user.id))


@router.post("/logout")
def logout(body: RefreshIn, user: User = Depends(get_current_user)):
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
        get_redis().setex(
            f"blacklist:{payload['jti']}",
            timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            "1",
        )
    except JWTError:
        pass  # already invalid — logout is idempotent
    return ok({"message": "Logged out"})


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return ok(_user_out(user))
