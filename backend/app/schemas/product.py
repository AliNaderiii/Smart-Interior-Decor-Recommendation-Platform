from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


def _taxonomy_styles() -> set[str]:
    path = Path(__file__).resolve().parents[2] / "seed_data/style_taxonomy.json"
    try:
        return {row["id"] for row in json.loads(path.read_text(encoding="utf-8"))["styles"]}
    except (OSError, KeyError, ValueError):
        # Offline/package fallback mirrors the committed taxonomy.
        return {"modern", "scandinavian", "industrial", "boho", "minimal", "classic"}


ALLOWED_STYLES = _taxonomy_styles()


def validate_styles(value: list[str] | None) -> list[str] | None:
    invalid = sorted(set(value or []) - ALLOWED_STYLES)
    if invalid:
        raise ValueError(f"Unknown styles: {', '.join(invalid)}")
    return value


class ProductIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    title_fa: str = ""
    category: str
    price_toman: int = Field(gt=0)
    image_url: str
    seller_link: str = ""
    colors: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    width_cm: int = 0
    depth_cm: int = 0
    height_cm: int = 0
    description: str = ""

    _styles_from_taxonomy = field_validator("styles")(validate_styles)


class ProductUpdate(BaseModel):
    title: str | None = None
    title_fa: str | None = None
    category: str | None = None
    price_toman: int | None = None
    image_url: str | None = None
    seller_link: str | None = None
    colors: list[str] | None = None
    styles: list[str] | None = None
    materials: list[str] | None = None
    patterns: list[str] | None = None
    width_cm: int | None = None
    depth_cm: int | None = None
    height_cm: int | None = None
    description: str | None = None
    is_verified: bool | None = None

    _styles_from_taxonomy = field_validator("styles")(validate_styles)


class ProductOut(BaseModel):
    id: str
    title: str
    title_fa: str
    category: str
    room_type: str
    price_toman: int
    image_url: str
    seller_link: str
    seller_link_ok: bool | None
    colors: list
    styles: list
    materials: list
    patterns: list
    width_cm: int
    depth_cm: int
    height_cm: int
    description: str
    extraction_confidence: float
    is_verified: bool

    model_config = {"from_attributes": True}
