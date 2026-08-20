from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.moodboard import Moodboard
    from app.models.project import Project
    from app.models.quiz import StyleQuiz
    from app.models.subscription import Subscription


class User(Base, UUIDPk, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(20), default="homeowner")  # homeowner|designer|admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    subscription: Mapped["Subscription | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    quizzes: Mapped[list["StyleQuiz"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    moodboards: Mapped[list["Moodboard"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="designer", cascade="all, delete-orphan"
    )
