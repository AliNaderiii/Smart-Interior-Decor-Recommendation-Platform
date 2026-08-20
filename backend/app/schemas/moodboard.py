from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.sanitize import SafeText

#: V2 (A04): fail closed on unknown fields so a future `**model_dump()` can
#: never become a mass-assignment hole. Phase 0B accepted
#: `{"title":"ok","is_admin":true,"user_id":"1001"}` with a 201.
STRICT = ConfigDict(extra="forbid")

#: V2 (A04): `title` is String(255) in the DB. Without a bound, a 5000-char
#: title reached the driver and returned 500. Now a clean 422.
Title = SafeText(max_length=200, min_length=1)


class MoodboardItem(BaseModel):
    model_config = STRICT

    product_id: str = Field(max_length=32)
    x: int = Field(default=0, ge=0, le=1000)
    y: int = Field(default=0, ge=0, le=1000)
    w: int = Field(default=2, ge=1, le=12)
    h: int = Field(default=2, ge=1, le=12)


class MoodboardIn(BaseModel):
    model_config = STRICT

    title: Title = "My Moodboard"
    quiz_id: str | None = Field(default=None, max_length=32)
    items: list[MoodboardItem] = Field(default_factory=list, max_length=100)
    shopping_list: list[str] = Field(default_factory=list, max_length=200)


class MoodboardUpdate(BaseModel):
    model_config = STRICT

    title: Title | None = None
    items: list[MoodboardItem] | None = Field(default=None, max_length=100)
    shopping_list: list[str] | None = Field(default=None, max_length=200)


class MoodboardOut(BaseModel):
    id: str
    user_id: str
    title: str
    quiz_id: str | None
    items: list
    shopping_list: list

    model_config = {"from_attributes": True}
