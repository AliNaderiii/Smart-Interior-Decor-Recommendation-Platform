from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.user import User


class Subscription(Base, UUIDPk, TimestampMixin):
    __tablename__ = "subscriptions"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    plan: Mapped[str] = mapped_column(String(20), default="free")  # free|pro
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="subscription")


class Payment(Base, UUIDPk, TimestampMixin):
    """Payment intent — stores ONLY the gateway authority/ref token.

    Never any card data (acceptance criterion: no payment info stored).
    """

    __tablename__ = "payments"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount_toman: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), default="zarinpal_sandbox")
    authority: Mapped[str] = mapped_column(String(64), index=True)  # gateway redirect token
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|paid|failed
    ref_id: Mapped[str] = mapped_column(String(64), default="")
