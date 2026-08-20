"""Per-user product feedback (👍/👎) — V2 Phase 3.

RESEARCH_V2 §2 (Havenly): feedback is a formal stage of the pipeline, not a
comment box. A thumbs button that only sets local state is a dead key, so this
table exists to make the signal durable and to let the recommender re-rank.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPk

if TYPE_CHECKING:
    pass


class ProductFeedback(Base, UUIDPk, TimestampMixin):
    __tablename__ = "product_feedback"
    __table_args__ = (
        # One verdict per user per product; a second thumb overwrites the first
        # rather than stacking, so a user cannot skew their own ranking by
        # clicking repeatedly.
        UniqueConstraint("user_id", "product_id", name="uq_feedback_user_product"),
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    # +1 = 👍, -1 = 👎. Integer rather than an enum so the recommender can use
    # it directly as a score term.
    signal: Mapped[int] = mapped_column(Integer)
    # Which category the product was shown in, for future per-category tuning.
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
