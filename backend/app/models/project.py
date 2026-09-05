from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import UniqueConstraint, DateTime, ForeignKey, String, Text
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
    # Lifecycle, persisted server-side. Previously this lived in the browser's
    # localStorage (see the honesty note in frontend/src/lib/projectStatus.ts),
    # so a designer who switched browsers lost every project's state and two
    # people could never agree on where a project stood.
    #   draft     — created, nothing shared yet
    #   shared    — a link has been sent to the client
    #   approved  — the client signed off on the selection
    #   completed — delivered / archived
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)

    designer: Mapped["User"] = relationship(back_populates="projects")
    quizzes: Mapped[list["StyleQuiz"]] = relationship(back_populates="project")


class ShareLink(Base, UUIDPk, TimestampMixin):
    """Signed public share token for read-only recommendation views."""

    __tablename__ = "share_links"

    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("style_quizzes.id", ondelete="CASCADE"))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClientApproval(Base, UUIDPk, TimestampMixin):
    """A client's verdict on one product inside a shared project.

    This is the piece that turns the share link from a read-only brochure into
    a two-way workflow — the single capability every competitor in this market
    (Planify, Mydoma, Programa, Studio Designer) builds their client portal
    around.

    Keyed by share token rather than user id on purpose: the client has no
    account and must not need one. The 256-bit token in the URL is the
    credential, exactly as in Planify's "Magic Link" model, so a client can
    review on a phone without a signup wall.

    One row per (share_link, product). Re-deciding updates the row rather than
    appending, so the designer always sees the client's current position and
    ``updated_at`` records when they last changed their mind.
    """

    __tablename__ = "client_approvals"
    __table_args__ = (
        UniqueConstraint("share_link_id", "product_id", name="uq_approval_link_product"),
    )

    share_link_id: Mapped[str] = mapped_column(
        ForeignKey("share_links.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    #: "approved" | "rejected"
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Free-text note from the client, e.g. "too dark for this room".
    comment: Mapped[str] = mapped_column(Text, default="")
