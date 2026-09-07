"""products: provenance + catalog-integrity columns (ADR-016)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-07

Adds the columns the catalog-integrity gate writes and the recommender reads:

* ``source`` / ``source_product_id`` — provenance (manual, synthetic-demo,
  perf, feed:<seller>, basalam …) and the seller's own id for idempotent
  re-imports;
* ``image_phash`` — perceptual hash for duplicate-image detection;
* ``price_checked_at`` — when the price was last confirmed with the seller;
* ``integrity_ok`` / ``integrity_reasons`` / ``integrity_checked_at`` — the
  last verdict of ``ai.catalog_integrity``. ``integrity_ok`` is nullable on
  purpose: legacy rows are NULL (= not yet evaluated, still eligible) until
  ``scripts/backfill_integrity.py`` has run; only ``False`` excludes a row.

Portable: plain SQL types + ``batch_alter_table`` so the SQLite dev path and
PostgreSQL run the same migration.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(
            sa.Column("source", sa.String(32), nullable=False, server_default="manual")
        )
        batch_op.add_column(sa.Column("source_product_id", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("image_phash", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("price_checked_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("integrity_ok", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("integrity_reasons", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("integrity_checked_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_products_image_phash", ["image_phash"])
        batch_op.create_index("ix_products_integrity_ok", ["integrity_ok"])


def downgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_index("ix_products_integrity_ok")
        batch_op.drop_index("ix_products_image_phash")
        batch_op.drop_column("integrity_checked_at")
        batch_op.drop_column("integrity_reasons")
        batch_op.drop_column("integrity_ok")
        batch_op.drop_column("price_checked_at")
        batch_op.drop_column("image_phash")
        batch_op.drop_column("source_product_id")
        batch_op.drop_column("source")
