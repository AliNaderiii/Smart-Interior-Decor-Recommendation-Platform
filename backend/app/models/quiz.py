from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import vector_type
from app.models.base import Base, TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class StyleQuiz(Base, UUIDPk, TimestampMixin):
    __tablename__ = "style_quizzes"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    client_name: Mapped[str] = mapped_column(String(255), default="")

    styles: Mapped[list] = mapped_column(JSON, default=list)          # ranked style prefs
    color_palette: Mapped[list] = mapped_column(JSON, default=list)   # ["#HEX", ...]
    room_width_cm: Mapped[int] = mapped_column(Integer, default=400)
    room_length_cm: Mapped[int] = mapped_column(Integer, default=500)
    budget_min_toman: Mapped[int] = mapped_column(Integer, default=0)
    budget_max_toman: Mapped[int] = mapped_column(Integer, default=100_000_000)
    materials: Mapped[list] = mapped_column(JSON, default=list)
    patterns: Mapped[list] = mapped_column(JSON, default=list)

    quiz_embedding: Mapped[list | None] = mapped_column(vector_type(), nullable=True)

    user: Mapped["User"] = relationship(back_populates="quizzes")
    project: Mapped["Project | None"] = relationship(back_populates="quizzes")
