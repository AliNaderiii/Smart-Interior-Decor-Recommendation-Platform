from __future__ import annotations

from pydantic import BaseModel, Field


class MoodboardItem(BaseModel):
    product_id: str
    x: int = 0
    y: int = 0
    w: int = Field(default=2, ge=1, le=12)
    h: int = Field(default=2, ge=1, le=12)


class MoodboardIn(BaseModel):
    title: str = "My Moodboard"
    quiz_id: str | None = None
    items: list[MoodboardItem] = Field(default_factory=list)
    shopping_list: list[str] = Field(default_factory=list)


class MoodboardUpdate(BaseModel):
    title: str | None = None
    items: list[MoodboardItem] | None = None
    shopping_list: list[str] | None = None


class MoodboardOut(BaseModel):
    id: str
    user_id: str
    title: str
    quiz_id: str | None
    items: list
    shopping_list: list

    model_config = {"from_attributes": True}
