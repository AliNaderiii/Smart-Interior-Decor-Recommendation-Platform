"""product link_status and link_checked_at columns for seller link quarantine (IR-S2-001)

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(sa.Column("link_status", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("link_checked_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_products_link_status", ["link_status"])


def downgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_index("ix_products_link_status")
        batch_op.drop_column("link_checked_at")
        batch_op.drop_column("link_status")
