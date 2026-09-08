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

    # ---- Catalog provenance & integrity (ADR-016, migration 0007) ---------
    # ``source``: who produced the row — "manual" (admin form/upload),
    # "synthetic-demo" (seed scripts; never inventory), "perf" (load harness),
    # or an importer id such as "feed:<seller>" / "basalam". ``source_product_id``
    # is the seller's own id so re-imports update instead of duplicating.
    source: Mapped[str] = mapped_column(String(32), default="manual", server_default="manual", nullable=False)
    source_product_id: Mapped[str | None] = mapped_column(String(128), default=None)
    # Perceptual hash of the product image (hex, 16 chars for a 64-bit dHash);
    # the duplicate-image check keys on it when present, on the URL otherwise.
    image_phash: Mapped[str | None] = mapped_column(String(32), default=None, index=True)
    # When the price was last confirmed against the seller. None = never.
    price_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Result of ai.catalog_integrity.integrity_decision at the last evaluation.
    # NULL = never evaluated (legacy rows) and is treated as eligible by the
    # recommender until backfill_integrity.py has run; False = excluded.
    integrity_ok: Mapped[bool | None] = mapped_column(Boolean, default=None, index=True)
    integrity_reasons: Mapped[list | None] = mapped_column(JSON, default=None)
    integrity_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    style_embedding: Mapped[list | None] = mapped_column(vector_type(), nullable=True)

    __table_args__ = (
        # Hot path for Stage A hard filter (ADR-005)
        Index("ix_products_filter", "room_type", "category", "is_verified", "price_toman"),
    )
