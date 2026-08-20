"""User endpoints incl. GDPR hard delete (DELETE /users/me)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.moodboard import Moodboard
from app.models.project import Project, ShareLink
from app.models.quiz import StyleQuiz
from app.models.subscription import Payment, Subscription
from app.models.user import User
from app.schemas.common import ok

router = APIRouter(prefix="/users", tags=["users"])


@router.delete("/me")
def gdpr_delete_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """GDPR right-to-erasure: hard-delete the user and ALL owned data."""
    uid = user.id
    db.execute(delete(ShareLink).where(ShareLink.created_by == uid))
    db.execute(delete(Payment).where(Payment.user_id == uid))
    db.execute(delete(Subscription).where(Subscription.user_id == uid))
    db.execute(delete(Moodboard).where(Moodboard.user_id == uid))
    db.execute(delete(StyleQuiz).where(StyleQuiz.user_id == uid))
    db.execute(delete(Project).where(Project.designer_id == uid))
    db.delete(db.get(User, uid))
    db.commit()
    return ok({"message": "All your data has been permanently deleted."})
