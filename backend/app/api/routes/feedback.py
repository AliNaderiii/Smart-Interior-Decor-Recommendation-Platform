"""Product feedback (👍/👎) — V2 Phase 3.

RESEARCH_V2 §2 (Havenly): "your honest feedback is key here" — the product
*forces* a like/dislike round-trip and the designer uses it to finalise. Our
equivalent: the signal is persisted and the recommender applies a per-user
boost/penalty at re-rank time, so the next set of recommendations is visibly
different. That is what separates a real feedback control from a dead key.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.feedback import ProductFeedback
from app.models.product import Product
from app.models.user import User
from app.schemas.common import ok
from app.schemas.feedback import FeedbackIn

router = APIRouter(tags=["feedback"])


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
def submit_feedback(
    body: FeedbackIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record or update this user's verdict on a product.

    Idempotent by (user, product): re-thumbing overwrites, and sending the same
    signal twice clears it (a toggle-off), which is what the UI's pressed-state
    button implies. Without the toggle, a mis-click would be permanent.
    """
    product = db.get(Product, body.product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    existing = db.execute(
        select(ProductFeedback).where(
            ProductFeedback.user_id == user.id,
            ProductFeedback.product_id == body.product_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.signal == body.signal:
            db.delete(existing)  # toggle off
            db.commit()
            return ok({"product_id": body.product_id, "signal": 0})
        existing.signal = body.signal
        existing.category = body.category or product.category
        db.commit()
        return ok({"product_id": body.product_id, "signal": existing.signal})

    row = ProductFeedback(
        user_id=user.id,
        product_id=body.product_id,
        signal=body.signal,
        category=body.category or product.category,
    )
    db.add(row)
    db.commit()
    return ok({"product_id": body.product_id, "signal": body.signal})


@router.get("/feedback")
def list_feedback(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All of this user's verdicts, so the UI can restore pressed state.

    Returned as a map rather than a list — the client looks these up by
    product id while rendering a grid, and a list would force an O(n) scan per
    card.
    """
    rows = db.execute(
        select(ProductFeedback).where(ProductFeedback.user_id == user.id)
    ).scalars().all()
    return ok({r.product_id: r.signal for r in rows})


@router.delete("/feedback", status_code=status.HTTP_204_NO_CONTENT)
def clear_feedback(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset all verdicts — the 'start over' escape hatch for a poisoned model."""
    db.execute(delete(ProductFeedback).where(ProductFeedback.user_id == user.id))
    db.commit()
    return None
