from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai.taxonomy import materials as taxonomy_materials
from ai.taxonomy import patterns as taxonomy_patterns
from ai.taxonomy import styles as taxonomy_styles
from app.schemas.sanitize import SafeText

#: Allowlists come from the taxonomy (seed_data/style_taxonomy.json) so the
#: quiz, the extractor and the seed data cannot drift apart. The identifiers
#: are stable IDs; the Persian labels live in the taxonomy, not in code.
ALLOWED_STYLES = frozenset(taxonomy_styles())
ALLOWED_MATERIALS = frozenset(taxonomy_materials())
ALLOWED_PATTERNS = frozenset(taxonomy_patterns())

_HEX_COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6}")


class QuizIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    styles: list[str] = Field(min_length=1, max_length=3)
    color_palette: list[str] = Field(default_factory=list, max_length=5)
    room_width_cm: int = Field(ge=100, le=3000)
    room_length_cm: int = Field(ge=100, le=3000)
    # int4 ceiling (PostgreSQL INTEGER): 2_000_000_000 toman is far above any
    # real furniture budget, and values beyond it would crash the Stage A query
    # with NumericValueOutOfRange instead of returning empty results.
    budget_min_toman: int = Field(ge=0, le=2_000_000_000)
    budget_max_toman: int = Field(gt=0, le=2_000_000_000)
    materials: list[str] = Field(default_factory=list, max_length=6)
    patterns: list[str] = Field(default_factory=list, max_length=3)
    project_id: str | None = None
    client_name: SafeText(max_length=200) = ""

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

    @field_validator("patterns")
    @classmethod
    def _patterns_allowed(cls, v: list[str]) -> list[str]:
        """Stage 04: patterns were unvalidated free strings; a typo silently
        scored 0 instead of failing fast with the taxonomy in the error."""
        bad = set(v) - ALLOWED_PATTERNS
        if bad:
            raise ValueError(
                f"unknown patterns: {sorted(bad)}; allowed: {sorted(ALLOWED_PATTERNS)}"
            )
        return v

    @field_validator("color_palette")
    @classmethod
    def _colors_wellformed(cls, v: list[str]) -> list[str]:
        """Stage 04: malformed hex silently scored as maximum color distance;
        reject at the boundary so the client can fix the payload."""
        for c in v:
            if not isinstance(c, str) or not _HEX_COLOR_RE.fullmatch(c):
                raise ValueError(f"colors must be #RRGGBB hex strings (got {c!r})")
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
