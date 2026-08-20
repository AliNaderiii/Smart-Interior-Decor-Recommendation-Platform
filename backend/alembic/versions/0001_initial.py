"""initial schema — pgvector extension, all tables, hot-path indexes

Revision ID: 0001
Revises:
Create Date: 2026-08-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

IS_PG = settings.is_postgres

if IS_PG:
    from pgvector.sqlalchemy import Vector

    def vec():
        return Vector(settings.EMBEDDING_DIM)
else:
    def vec():
        return sa.Text()


def upgrade() -> None:
    if IS_PG:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("role", sa.String(20), nullable=False, server_default="homeowner"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("title_fa", sa.String(255), nullable=False, server_default=""),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("room_type", sa.String(50), nullable=False, server_default="living_room"),
        sa.Column("price_toman", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("seller_link", sa.Text(), nullable=False, server_default=""),
        sa.Column("seller_link_ok", sa.Boolean(), nullable=True),
        sa.Column("colors", sa.JSON(), nullable=False),
        sa.Column("styles", sa.JSON(), nullable=False),
        sa.Column("materials", sa.JSON(), nullable=False),
        sa.Column("patterns", sa.JSON(), nullable=False),
        sa.Column("width_cm", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("depth_cm", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("height_cm", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("extraction_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("extraction_raw", sa.JSON(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("style_embedding", vec(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_room_type", "products", ["room_type"])
    op.create_index("ix_products_price_toman", "products", ["price_toman"])
    op.create_index("ix_products_is_verified", "products", ["is_verified"])
    op.create_index(
        "ix_products_filter", "products",
        ["room_type", "category", "is_verified", "price_toman"],
    )
    if IS_PG:
        # ANN index for Stage B semantic search
        op.execute(
            "CREATE INDEX ix_products_style_embedding ON products "
            "USING hnsw (style_embedding vector_cosine_ops)"
        )

    op.create_table(
        "projects",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("designer_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("client_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("client_email", sa.String(255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_projects_designer_id", "projects", ["designer_id"])

    op.create_table(
        "style_quizzes",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("client_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("styles", sa.JSON(), nullable=False),
        sa.Column("color_palette", sa.JSON(), nullable=False),
        sa.Column("room_width_cm", sa.Integer(), nullable=False, server_default="400"),
        sa.Column("room_length_cm", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("budget_min_toman", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget_max_toman", sa.Integer(), nullable=False, server_default="100000000"),
        sa.Column("materials", sa.JSON(), nullable=False),
        sa.Column("patterns", sa.JSON(), nullable=False),
        sa.Column("quiz_embedding", vec(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_style_quizzes_user_id", "style_quizzes", ["user_id"])

    op.create_table(
        "moodboards",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False, server_default="My Moodboard"),
        sa.Column("quiz_id", sa.String(32), sa.ForeignKey("style_quizzes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("shopping_list", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_moodboards_user_id", "moodboards", ["user_id"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan", sa.String(20), nullable=False, server_default="free"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"], unique=True)

    op.create_table(
        "payments",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_toman", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False, server_default="zarinpal_sandbox"),
        sa.Column("authority", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("ref_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_authority", "payments", ["authority"])

    op.create_table(
        "share_links",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("quiz_id", sa.String(32), sa.ForeignKey("style_quizzes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_share_links_token", "share_links", ["token"], unique=True)


def downgrade() -> None:
    for table in (
        "share_links", "payments", "subscriptions", "moodboards",
        "style_quizzes", "projects", "products", "users",
    ):
        op.drop_table(table)
