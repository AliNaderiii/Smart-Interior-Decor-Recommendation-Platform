"""feedback_events — append-only behavioural event stream (ADR-014)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-06

``docs/ai/feedback-events.md`` designed this table in Stage 04 as the data a
future learning stage would need ("impression is the denominator"); nothing
captured it. The thumbs (``product_feedback``) stay the source of truth for
the bounded re-rank; this table only records behaviour and is read by an
admin summary endpoint — no ranking code consumes it yet, and none is claimed.

Portable: plain SQL types, no dialect-specific DDL, so the documented SQLite
path and PostgreSQL run the same migration.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id", sa.String(32),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("session_id", sa.String(32), nullable=False),
        sa.Column("quiz_id", sa.String(32), nullable=True),
        sa.Column(
            "product_id", sa.String(32),
            sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_context", sa.String(24), nullable=False),
        sa.Column("weights_version", sa.String(32), nullable=True),
        sa.Column("sample_rate", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_feedback_events_user_id", "feedback_events", ["user_id"])
    op.create_index("ix_feedback_events_quiz_id", "feedback_events", ["quiz_id"])
    op.create_index("ix_feedback_events_event_type", "feedback_events", ["event_type"])
    op.create_index("ix_feedback_events_created_at", "feedback_events", ["created_at"])
    op.create_index(
        "ix_feedback_events_session_created", "feedback_events", ["session_id", "created_at"]
    )
    op.create_index(
        "ix_feedback_events_product_type", "feedback_events", ["product_id", "event_type"]
    )


def downgrade() -> None:
    for name in (
        "ix_feedback_events_product_type",
        "ix_feedback_events_session_created",
        "ix_feedback_events_created_at",
        "ix_feedback_events_event_type",
        "ix_feedback_events_quiz_id",
        "ix_feedback_events_user_id",
    ):
        op.drop_index(name, table_name="feedback_events")
    op.drop_table("feedback_events")
