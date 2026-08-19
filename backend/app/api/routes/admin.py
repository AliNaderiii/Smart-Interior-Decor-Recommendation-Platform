"""Admin: users, subscriptions, style taxonomy, pending verifications."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.product import MATERIALS, STYLES, Product
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.common import ok

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return ok([
        {
            "id": u.id, "email": u.email, "full_name": u.full_name,
            "role": u.role, "is_active": u.is_active,
            "subscription_plan": u.subscription.plan if u.subscription else "free",
            "subscription_active": bool(u.subscription and u.subscription.is_active),
            "created_at": u.created_at.isoformat(),
        }
        for u in rows
    ])


class UserPatch(BaseModel):
    is_active: bool | None = None
    role: str | None = None


@router.patch("/users/{user_id}")
def patch_user(user_id: str, body: UserPatch, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.role is not None:
        if body.role not in ("homeowner", "designer", "admin"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad role")
        user.role = body.role
    db.commit()
    return ok({"id": user.id, "role": user.role, "is_active": user.is_active})


@router.get("/subscriptions")
def list_subscriptions(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.execute(
        select(Subscription, User.email).join(User, Subscription.user_id == User.id)
    ).all()
    return ok([
        {
            "id": s.id, "user_email": email, "plan": s.plan, "is_active": s.is_active,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
        }
        for s, email in rows
    ])


@router.get("/taxonomy")
def get_taxonomy(_: User = Depends(require_admin)):
    return ok({"styles": STYLES, "materials": MATERIALS})


@router.get("/stats")
def stats(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return ok({
        "users": db.scalar(select(func.count(User.id))),
        "products": db.scalar(select(func.count(Product.id))),
        "verified_products": db.scalar(
            select(func.count(Product.id)).where(Product.is_verified.is_(True))
        ),
        "pending_products": db.scalar(
            select(func.count(Product.id)).where(Product.is_verified.is_(False))
        ),
        "active_subscriptions": db.scalar(
            select(func.count(Subscription.id)).where(Subscription.is_active.is_(True))
        ),
    })
