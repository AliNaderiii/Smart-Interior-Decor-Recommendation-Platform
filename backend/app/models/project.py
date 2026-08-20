from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.quiz import StyleQuiz
    from app.models.user import User


class Project(Base, UUIDPk, TimestampMixin):
    """Designer (B2B2C) project — one client engagement."""

    __tablename__ = "projects"

    designer_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), default="")
    client_email: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    designer: Mapped["User"] = relationship(back_populates="projects")
    quizzes: Mapped[list["StyleQuiz"]] = relationship(back_populates="project")


class ShareLink(Base, UUIDPk, TimestampMixin):
    """Signed public share token for read-only recommendation views."""

    __tablename__ = "share_links"

    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("style_quizzes.id", ondelete="CASCADE"))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
