"""designer workflow: moodboard→project link, real project status, client approvals

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-05

Closes the three structural gaps that made the designer portal a shell:

1. ``moodboards.project_id`` — a project could hold quizzes but none of the
   actual work product, so opening a project showed an empty container.
2. ``projects.status`` — lifecycle state lived in the browser's localStorage
   (see frontend/src/lib/projectStatus.ts), so it vanished when the designer
   switched machines.
3. ``client_approvals`` — the share link was read-only. Every competitor in
   this market builds their client portal around item-level approval, which
   is what turns a shared link into a workflow.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("moodboards") as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.String(32), nullable=True))
        batch_op.create_index("ix_moodboards_project_id", ["project_id"])
        batch_op.create_foreign_key(
            "fk_moodboards_project_id", "projects", ["project_id"], ["id"],
            ondelete="SET NULL",
        )

    # server_default backfills existing rows in one statement; the column stays
    # NOT NULL so application code never has to handle a missing status.
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(16), nullable=False, server_default="draft")
        )
        batch_op.create_index("ix_projects_status", ["status"])

    op.create_table(
        "client_approvals",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("share_link_id", sa.String(32), nullable=False),
        sa.Column("product_id", sa.String(32), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["share_link_id"], ["share_links.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("share_link_id", "product_id", name="uq_approval_link_product"),
    )
    op.create_index("ix_client_approvals_share_link_id", "client_approvals", ["share_link_id"])
    op.create_index("ix_client_approvals_product_id", "client_approvals", ["product_id"])


def downgrade() -> None:
    op.drop_table("client_approvals")
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_index("ix_projects_status")
        batch_op.drop_column("status")
    with op.batch_alter_table("moodboards") as batch_op:
        batch_op.drop_constraint("fk_moodboards_project_id", type_="foreignkey")
        batch_op.drop_index("ix_moodboards_project_id")
        batch_op.drop_column("project_id")
