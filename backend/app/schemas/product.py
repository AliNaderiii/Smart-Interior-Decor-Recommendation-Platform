"""Product schemas.

Stage 03 hardening (probe `X-01`, `X-02`, `V-01`, `V-03`):

* ``extra="forbid"`` — both write models were splatted into ``Product(**dump)``
  / ``setattr`` loops with no unknown-field rejection, so any future column
  became remotely settable the moment it was added (`V-01` observed a `201` for
  a body containing `id` and `is_verified`).
* URL fields are validated as **safe absolute http(s) URLs**. `seller_link` is
  rendered directly into `<a href>` in three SPA views including the
  *unauthenticated* share page, so `javascript:` there was stored XSS
  (`X-01`); both URL fields are also fetched server-side, so they are an SSRF
  sink (see ``app.core.url_safety``).
* Free text is HTML-stripped and length-bounded. Admin-entered copy is not
  trusted input: an admin session is exactly what an attacker escalates *to*,
  and the same fields are populated from AI output on the upload path.
* ``category`` is validated against the catalog taxonomy instead of being a
  free string that silently created an unreachable partition of the catalog.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.url_safety import UnsafeUrl, safe_optional_url, validate_public_url
from app.schemas.sanitize import SafeText

STRICT = ConfigDict(extra="forbid")


def _taxonomy_styles() -> set[str]:
    path = Path(__file__).resolve().parents[2] / "seed_data/style_taxonomy.json"
    try:
        return {row["id"] for row in json.loads(path.read_text(encoding="utf-8"))["styles"]}
    except (OSError, KeyError, ValueError):
        # Offline/package fallback mirrors the committed taxonomy.
        return {"modern", "scandinavian", "industrial", "boho", "minimal", "classic"}


ALLOWED_STYLES = _taxonomy_styles()

#: Mirrors `app.models.product.CATEGORIES`; imported lazily to avoid a schema ->
#: model import cycle at module load.
def _allowed_categories() -> set[str]:
    try:
        from app.models.product import CATEGORIES

        return set(CATEGORIES)
    except Exception:  # pragma: no cover - defensive
        return {"sofa", "coffee_table", "rug", "lighting", "chair", "storage", "decor"}


ALLOWED_CATEGORIES = _allowed_categories()

#: Bounded so a list cannot be used as an unbounded write primitive.
_TAG_LIST = Field(default_factory=list, max_length=12)


def validate_styles(value: list[str] | None) -> list[str] | None:
    invalid = sorted(set(value or []) - ALLOWED_STYLES)
    if invalid:
        raise ValueError(f"Unknown styles: {', '.join(invalid)}")
    return value


def validate_category(value: str | None) -> str | None:
    if value is None:
        return value
    if value not in ALLOWED_CATEGORIES:
        raise ValueError(f"Unknown category: {value}")
    return value


def _image_url(value: str) -> str:
    try:
        return validate_public_url(value, resolve=False, field="image_url")
    except UnsafeUrl as exc:
        raise ValueError(str(exc)) from exc


def _seller_link(value: str | None) -> str:
    try:
        return safe_optional_url(value, field="seller_link")
    except UnsafeUrl as exc:
        raise ValueError(str(exc)) from exc


def _bounded_tags(value: list[str] | None) -> list[str] | None:
    """Tags are short identifiers, not free text — bound and strip them."""
    if value is None:
        return None
    cleaned = []
    for item in value:
        text = str(item).strip()[:64]
        if text:
            cleaned.append(text)
    return cleaned


class ProductIn(BaseModel):
    model_config = STRICT

    title: SafeText(max_length=200, min_length=1)
    title_fa: SafeText(max_length=200) = ""
    category: str = Field(max_length=64)
    price_toman: int = Field(gt=0, le=10_000_000_000)
    image_url: str = Field(max_length=2048)
    seller_link: str = Field(default="", max_length=2048)
    colors: list[str] = _TAG_LIST
    styles: list[str] = _TAG_LIST
    materials: list[str] = _TAG_LIST
    patterns: list[str] = _TAG_LIST
    width_cm: int = Field(default=0, ge=0, le=100_000)
    depth_cm: int = Field(default=0, ge=0, le=100_000)
    height_cm: int = Field(default=0, ge=0, le=100_000)
    description: SafeText(max_length=2000) = ""

    _styles_from_taxonomy = field_validator("styles")(validate_styles)
    _category_allowed = field_validator("category")(validate_category)
    _image_url_safe = field_validator("image_url")(_image_url)
    _seller_link_safe = field_validator("seller_link")(_seller_link)
    _tags_bounded = field_validator("colors", "materials", "patterns")(_bounded_tags)


class ProductUpdate(BaseModel):
    model_config = STRICT

    title: SafeText(max_length=200, min_length=1) | None = None
    title_fa: SafeText(max_length=200) | None = None
    category: str | None = Field(default=None, max_length=64)
    price_toman: int | None = Field(default=None, gt=0, le=10_000_000_000)
    image_url: str | None = Field(default=None, max_length=2048)
    seller_link: str | None = Field(default=None, max_length=2048)
    colors: list[str] | None = Field(default=None, max_length=12)
    styles: list[str] | None = Field(default=None, max_length=12)
    materials: list[str] | None = Field(default=None, max_length=12)
    patterns: list[str] | None = Field(default=None, max_length=12)
    width_cm: int | None = Field(default=None, ge=0, le=100_000)
    depth_cm: int | None = Field(default=None, ge=0, le=100_000)
    height_cm: int | None = Field(default=None, ge=0, le=100_000)
    description: SafeText(max_length=2000) | None = None
    is_verified: bool | None = None

    _styles_from_taxonomy = field_validator("styles")(validate_styles)
    _category_allowed = field_validator("category")(validate_category)
    _tags_bounded = field_validator("colors", "materials", "patterns")(_bounded_tags)

    @field_validator("image_url")
    @classmethod
    def _image_url_safe(cls, value: str | None) -> str | None:
        return None if value is None else _image_url(value)

    @field_validator("seller_link")
    @classmethod
    def _seller_link_safe(cls, value: str | None) -> str | None:
        return None if value is None else _seller_link(value)


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
