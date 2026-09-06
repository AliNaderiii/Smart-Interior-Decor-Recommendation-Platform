"""Behavioural event stream (ADR-014) — the table `docs/ai/feedback-events.md`
designed before any learning could be attempted.

A thumb (``product_feedback``) is a *decision*; this table records
*behaviour*: what was shown (impression — the denominator), what was clicked,
saved, shared. Append-only by design — history is the point, so there are no
upserts and no updated_at.

Design rules carried over from the spec:

* no PII and no free text — the event references the quiz and product by id;
* every row carries ``position`` (rank at display time) and
  ``weights_version`` (which recommender config produced the list) so
  position bias and A/B attribution can be handled offline later;
* ``sample_rate`` is stored per row so a future sampled impression logger
  stays fathomable (1.0 = every impression written).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk, utcnow

#: Closed vocabulary — anything else is a 422 at the API boundary.
EVENT_TYPES: tuple[str, ...] = (
    "impression",
    "click",
    "like",
    "dislike",
    "unlike",
    "save",
    "share",
    "purchase_click",
)

PAGE_CONTEXTS: tuple[str, ...] = ("recommend", "moodboard", "share", "catalog", "visual_search")


class FeedbackEvent(Base, UUIDPk):
    __tablename__ = "feedback_events"
    __table_args__ = (
        # The two questions the summary endpoint asks: "what happened in this
        # session?" and "what happened to this product, per type, over time?"
        Index("ix_feedback_events_session_created", "session_id", "created_at"),
        Index("ix_feedback_events_product_type", "product_id", "event_type"),
        Index("ix_feedback_events_created_at", "created_at"),
    )

    # Nullable on purpose: anonymous share-page viewers produce events too.
    # ON DELETE SET NULL keeps the aggregate history when a user is erased;
    # the GDPR erasure path nulls it explicitly too (SQLite without FK pragma).
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Client-generated, per browsing session (sessionStorage), 32 hex chars.
    session_id: Mapped[str] = mapped_column(String(32), nullable=False)
    quiz_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    # 1-based rank at display time; 0 when not applicable (e.g. moodboard).
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_context: Mapped[str] = mapped_column(String(24), nullable=False)
    weights_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sample_rate: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
