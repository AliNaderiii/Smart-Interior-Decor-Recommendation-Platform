"""Request/response shapes for the behavioural event stream (ADR-014)."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.feedback_event import EVENT_TYPES, PAGE_CONTEXTS

EventType = Literal[
    "impression", "click", "like", "dislike", "unlike", "save", "share", "purchase_click"
]
PageContext = Literal["recommend", "moodboard", "share", "catalog", "visual_search"]

assert set(EventType.__args__) == set(EVENT_TYPES)  # type: ignore[attr-defined]
assert set(PageContext.__args__) == set(PAGE_CONTEXTS)  # type: ignore[attr-defined]

_HEX32 = re.compile(r"^[0-9a-f]{32}$")

#: One request may carry a whole screen's worth of impressions (5 per
#: category × 7 categories = 35) plus a few clicks; anything beyond this is
#: a misbehaving client, not a bigger screen.
MAX_BATCH = 100


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=64)
    event_type: EventType
    page_context: PageContext
    # 1-based rank at display time; 0 = not ranked (moodboard, share page).
    position: int = Field(default=0, ge=0, le=100)
    quiz_id: str | None = Field(default=None, max_length=32)
    weights_version: str | None = Field(default=None, max_length=32)


class EventBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Client-generated per browsing session (crypto.randomUUID without
    # dashes). Validated to a fixed alphabet so it can never carry text.
    session_id: str = Field(min_length=32, max_length=32)
    events: list[EventIn] = Field(min_length=1, max_length=MAX_BATCH)

    @field_validator("session_id")
    @classmethod
    def _hex(cls, value: str) -> str:
        if not _HEX32.match(value):
            raise ValueError("session_id must be 32 lowercase hex characters")
        return value
