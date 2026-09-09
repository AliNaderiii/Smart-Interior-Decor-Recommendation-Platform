"""bootstrap_runs — durable once-only record for the container entrypoint (ADR-017)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-08

``scripts/entrypoint.py`` runs migrations, the catalog bootstrap and the
integrity backfill on every container boot because a shell-less PaaS offers
no other hook. A labelled catalog *replacement* must nevertheless happen once
per label per database, whatever the platform does with restarts, rollbacks
and replicas — so the lock is a unique row here, not a file or an env var.

Portable: plain SQL types, no dialect-specific DDL.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent on purpose — same reasoning as 0006: every seed script calls
    # ``Base.metadata.create_all``, so a database first touched by newer code
    # may already own this table when Alembic gets to run.
    if sa.inspect(op.get_bind()).has_table("bootstrap_runs"):
        return
    op.create_table(
        "bootstrap_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("label", sa.String(64), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bootstrap_runs_action", "bootstrap_runs", ["action"])
    op.create_index("ix_bootstrap_runs_label", "bootstrap_runs", ["label"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_bootstrap_runs_label", table_name="bootstrap_runs")
    op.drop_index("ix_bootstrap_runs_action", table_name="bootstrap_runs")
    op.drop_table("bootstrap_runs")
