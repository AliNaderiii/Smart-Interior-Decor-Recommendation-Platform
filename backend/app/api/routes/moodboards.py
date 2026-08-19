"""Moodboard CRUD — items stored as JSONB layout {product_id,x,y,w,h}."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.moodboard import Moodboard
from app.models.product import Product
from app.models.user import User
from app.schemas.common import ok
from app.schemas.moodboard import MoodboardIn, MoodboardOut, MoodboardUpdate

router = APIRouter(prefix="/moodboards", tags=["moodboards"])


def _owned(db: Session, moodboard_id: str, user: User) -> Moodboard:
    board = db.get(Moodboard, moodboard_id)
    if board is None or board.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Moodboard not found")
    return board


@router.post("", status_code=status.HTTP_201_CREATED)
def create_moodboard(body: MoodboardIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    board = Moodboard(
        user_id=user.id,
        title=body.title,
        quiz_id=body.quiz_id,
        items=[i.model_dump() for i in body.items],
        shopping_list=body.shopping_list,
    )
    db.add(board)
    db.commit()
    return ok(MoodboardOut.model_validate(board).model_dump())


@router.get("")
def list_moodboards(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Moodboard).where(Moodboard.user_id == user.id).order_by(Moodboard.created_at.desc())
    ).all()
    return ok([MoodboardOut.model_validate(b).model_dump() for b in rows])


@router.get("/{moodboard_id}")
def get_moodboard(moodboard_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    board = _owned(db, moodboard_id, user)
    product_ids = {i["product_id"] for i in board.items} | set(board.shopping_list)
    products = db.scalars(select(Product).where(Product.id.in_(product_ids))).all() if product_ids else []
    from app.schemas.product import ProductOut

    return ok({
        **MoodboardOut.model_validate(board).model_dump(),
        "products": {p.id: ProductOut.model_validate(p).model_dump() for p in products},
    })


@router.patch("/{moodboard_id}")
def update_moodboard(
    moodboard_id: str,
    body: MoodboardUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    board = _owned(db, moodboard_id, user)
    if body.title is not None:
        board.title = body.title
    if body.items is not None:
        board.items = [i.model_dump() for i in body.items]
    if body.shopping_list is not None:
        board.shopping_list = body.shopping_list
    db.commit()
    return ok(MoodboardOut.model_validate(board).model_dump())


@router.delete("/{moodboard_id}")
def delete_moodboard(moodboard_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    board = _owned(db, moodboard_id, user)
    db.delete(board)
    db.commit()
    return ok({"message": "deleted"})
