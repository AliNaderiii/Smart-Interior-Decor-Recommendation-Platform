"""Subscriptions + Zarinpal/Zibal payment redirect flow (no card storage)."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.base import utcnow
from app.models.subscription import Payment, Subscription
from app.models.user import User
from app.schemas.common import ok
from app.services.payment import PRO_PLAN_PRICE_TOMAN, get_gateway

router = APIRouter(tags=["subscriptions"])


class VerifyIn(BaseModel):
    # Stage 03 (T-17/T-23): unbounded strings on a payment callback body reach
    # the driver and, on PostgreSQL, produce a 500 rather than a 422. The
    # gateway's authority is a short opaque token; bound it and reject anything
    # the client invented.
    model_config = ConfigDict(extra="forbid")

    authority: str = Field(min_length=1, max_length=128)
    status: str = Field(default="OK", max_length=32)


@router.get("/subscriptions/me")
def my_subscription(user: User = Depends(get_current_user)):
    sub = user.subscription
    return ok({
        "plan": sub.plan if sub else "free",
        "is_active": bool(sub and sub.is_active),
        "expires_at": sub.expires_at.isoformat() if sub and sub.expires_at else None,
        "pro_price_toman": PRO_PLAN_PRICE_TOMAN,
    })


@router.post("/payment/request", status_code=status.HTTP_201_CREATED)
def request_payment(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Start a Pro upgrade: create a payment intent, return gateway redirect URL."""
    authority, redirect_url = get_gateway().request_payment(
        PRO_PLAN_PRICE_TOMAN, "Smart Decor Pro subscription (30 days)"
    )
    payment = Payment(
        user_id=user.id,
        amount_toman=PRO_PLAN_PRICE_TOMAN,
        provider="configured",
        authority=authority,
        status="pending",
    )
    db.add(payment)
    db.commit()
    return ok({"authority": authority, "redirect_url": redirect_url})


@router.post("/payment/verify")
def verify_payment(body: VerifyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Gateway callback verification — activates the Pro subscription."""
    payment = db.scalar(
        select(Payment).where(Payment.authority == body.authority, Payment.user_id == user.id)
    )
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if payment.status == "paid":
        return ok({"status": "paid", "ref_id": payment.ref_id})
    if body.status != "OK":
        payment.status = "failed"
        db.commit()
        return ok({"status": "failed"})

    paid, ref_id = get_gateway().verify_payment(body.authority, payment.amount_toman)
    if not paid:
        payment.status = "failed"
        db.commit()
        return ok({"status": "failed"})

    payment.status = "paid"
    payment.ref_id = ref_id
    sub = user.subscription or Subscription(user_id=user.id)
    sub.plan = "pro"
    sub.is_active = True
    sub.expires_at = utcnow() + timedelta(days=30)
    db.add(sub)
    db.commit()
    return ok({"status": "paid", "ref_id": ref_id, "expires_at": sub.expires_at.isoformat()})
