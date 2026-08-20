"""audit_logs table — OWASP A09 security logging

Phase 1 (V2 strict mode). Phase 0B found no forensic trail for auth events;
this migration adds the append-only audit table with the two indexes the ops
queries need ("recent activity for user X", "failed logins in last 15 min").

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False, server_default=""),
        sa.Column("ip", sa.String(45), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"])
    op.create_index("ix_audit_logs_action_created", "audit_logs", ["action", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_action_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
