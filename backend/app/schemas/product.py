from __future__ import annotations

from pydantic import BaseModel, Field


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
