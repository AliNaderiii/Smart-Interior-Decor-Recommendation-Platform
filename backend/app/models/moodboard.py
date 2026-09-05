from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.user import User


class Moodboard(Base, UUIDPk, TimestampMixin):
    __tablename__ = "moodboards"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="My Moodboard")
    quiz_id: Mapped[str | None] = mapped_column(
        ForeignKey("style_quizzes.id", ondelete="SET NULL"), nullable=True
    )
    # A designer's board belongs to the client project it was made for.
    # Without this a project could hold quizzes but none of the actual work
    # product, so the designer portal listed projects that contained nothing.
    # SET NULL rather than CASCADE: deleting a project must not destroy the
    # board, which the designer may still want in their own library.
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # items: [{product_id, x, y, w, h}] — react-grid-layout JSONB
    items: Mapped[list] = mapped_column(JSON, default=list)
    # shopping list: [product_id, ...]
    shopping_list: Mapped[list] = mapped_column(JSON, default=list)

    user: Mapped["User"] = relationship(back_populates="moodboards")
