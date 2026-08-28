from __future__ import annotations

from datetime import datetime
from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import vector_type
from app.models.base import Base, TimestampMixin, UUIDPk

CATEGORIES = [
    "sofa",
    "coffee_table",
    "rug",
    "lighting",
    "chair",
    "storage",
    "decor",
]

STYLES = ["modern", "scandinavian", "industrial", "boho", "minimal", "classic"]
MATERIALS = ["wood", "metal", "fabric", "leather", "glass", "rattan"]


class Product(Base, UUIDPk, TimestampMixin):
    __tablename__ = "products"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    title_fa: Mapped[str] = mapped_column(String(255), default="")
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    room_type: Mapped[str] = mapped_column(String(50), default="living_room", index=True)
    price_toman: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    seller_link: Mapped[str] = mapped_column(Text, default="")
    seller_link_ok: Mapped[bool | None] = mapped_column(Boolean, default=None)
    link_status: Mapped[str | None] = mapped_column(String(32), default=None, index=True)
    link_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # AI-extracted features (human-in-the-loop verified via is_verified)
    colors: Mapped[list] = mapped_column(JSON, default=list)      # ["#A0522D", ...]
    styles: Mapped[list] = mapped_column(JSON, default=list)      # ["modern", ...]
    materials: Mapped[list] = mapped_column(JSON, default=list)   # ["wood", ...]
    patterns: Mapped[list] = mapped_column(JSON, default=list)    # ["solid", "geometric", ...]
    width_cm: Mapped[int] = mapped_column(Integer, default=0)
    depth_cm: Mapped[int] = mapped_column(Integer, default=0)
    height_cm: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    extraction_raw: Mapped[dict] = mapped_column(JSON, default=dict)

    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    style_embedding: Mapped[list | None] = mapped_column(vector_type(), nullable=True)

    __table_args__ = (
        # Hot path for Stage A hard filter (ADR-005)
        Index("ix_products_filter", "room_type", "category", "is_verified", "price_toman"),
    )
