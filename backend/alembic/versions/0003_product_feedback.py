"""product_feedback table — 👍/👎 signals that re-rank recommendations

Phase 3 (V2 strict mode). RESEARCH_V2 §2 (Havenly): the feedback round-trip is
a formal pipeline stage. Without persistence a thumbs button is a dead key.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_feedback",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.String(32),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_product_feedback_user_id", "product_feedback", ["user_id"])
    op.create_index("ix_product_feedback_product_id", "product_feedback", ["product_id"])
    # One verdict per user per product — a repeated thumb overwrites rather
    # than stacking, so a user cannot skew their own ranking by spamming.
    op.create_unique_constraint(
        "uq_feedback_user_product", "product_feedback", ["user_id", "product_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_feedback_user_product", "product_feedback", type_="unique")
    op.drop_index("ix_product_feedback_product_id", table_name="product_feedback")
    op.drop_index("ix_product_feedback_user_id", table_name="product_feedback")
    op.drop_table("product_feedback")
