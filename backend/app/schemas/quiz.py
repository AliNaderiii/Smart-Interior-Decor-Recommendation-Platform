from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

ALLOWED_STYLES = {"modern", "scandinavian", "industrial", "boho", "minimal", "classic"}
ALLOWED_MATERIALS = {"wood", "metal", "fabric", "leather", "glass", "rattan"}


class QuizIn(BaseModel):
    styles: list[str] = Field(min_length=1, max_length=3)
    color_palette: list[str] = Field(default_factory=list, max_length=5)
    room_width_cm: int = Field(ge=100, le=3000)
    room_length_cm: int = Field(ge=100, le=3000)
    budget_min_toman: int = Field(ge=0)
    budget_max_toman: int = Field(gt=0)
    materials: list[str] = Field(default_factory=list, max_length=6)
    patterns: list[str] = Field(default_factory=list, max_length=3)
    project_id: str | None = None
    client_name: str = ""

    @field_validator("styles")
    @classmethod
    def _styles_allowed(cls, v: list[str]) -> list[str]:
        bad = set(v) - ALLOWED_STYLES
        if bad:
            raise ValueError(f"unknown styles: {sorted(bad)}")
        return v

    @field_validator("materials")
    @classmethod
    def _materials_allowed(cls, v: list[str]) -> list[str]:
        bad = set(v) - ALLOWED_MATERIALS
        if bad:
            raise ValueError(f"unknown materials: {sorted(bad)}")
        return v

    @field_validator("budget_max_toman")
    @classmethod
    def _budget_order(cls, v: int, info) -> int:
        lo = info.data.get("budget_min_toman", 0)
        if v <= lo:
            raise ValueError("budget_max_toman must be greater than budget_min_toman")
        return v


class QuizOut(QuizIn):
    id: str
    user_id: str

    model_config = {"from_attributes": True}
