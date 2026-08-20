"""Feedback schemas — strict, per Phase 1 hardening conventions."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FeedbackIn(BaseModel):
    # extra="forbid" mirrors the Phase 1 decision: an unknown field is a client
    # bug or an attack, never something to silently ignore.
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=64)
    # Literal rather than int so 0 / 5 / -99 are rejected at the edge.
    signal: Literal[-1, 1]
    category: str | None = Field(default=None, max_length=64)
