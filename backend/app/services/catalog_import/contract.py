"""The importer's input contract: what a seller row must carry to become a product.

Every adapter (CSV/JSON file, Basalam OpenAPI, later Digikala affiliate) ends
in :func:`normalize_row`, which turns a loosely typed mapping into a
:class:`FeedRow` or rejects it with machine-readable problem codes. The
normaliser is deliberately strict about *structure* (a price must be a
positive integer, an image must be an absolute http(s) URL) and deliberately
silent about *truth* — whether the picture really shows a sofa is the job of
the vision check and the ADR-016 integrity gate downstream. Nothing here
fills a blank with a plausible value: an unknown dimension stays ``0``
(= unknown), an unmapped category is a rejection, not a guess.

Persian input is first-class: digits (``۳۴٬۰۰۰٬۰۰۰``), the Persian thousands
separator and the taxonomy's Persian labels (``مبل``, ``فرش`` …) are accepted
everywhere a number or a category is expected.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ai import taxonomy as tax
from app.core.url_safety import UnsafeUrl, validate_public_url
from app.schemas.sanitize import strip_html

#: ``products.source`` is ``String(32)``; file feeds are ``feed:<slug>``.
SOURCE_MAX_LEN = 32
FEED_PREFIX = "feed:"
SELLER_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,25}$")
SOURCE_PRODUCT_ID_MAX_LEN = 128
TITLE_MAX_LEN = 255
DESCRIPTION_MAX_LEN = 2000
MAX_TAGS = 12
MAX_DIMENSION_CM = 100_000  # mirrors ProductIn bounds
MAX_PRICE_TOMAN = 10_000_000_000

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NUMBER_JUNK_RE = re.compile(r"[\s,٬_']+")
_LIST_SPLIT_RE = re.compile(r"[|;,،/]+")
_DIMS_SPLIT_RE = re.compile(r"\s*[x×*]\s*|\s*در\s*")

#: Seller category labels → taxonomy ids. Built from the taxonomy's own
#: Persian/English names plus the everyday retail words Iranian sellers use.
#: This is a *declared-label* mapping — the seller says "فرش", we file it
#: under ``rug``. It never looks at titles or pictures.
_CATEGORY_ALIASES: dict[str, str] = {
    "sofa": "sofa", "couch": "sofa", "مبل": "sofa", "مبلمان": "sofa", "مبل راحتی": "sofa",
    "کاناپه": "sofa", "مبل ال": "sofa", "مبل تختخوابشو": "sofa", "مبل تخت‌خواب‌شو": "sofa",
    "coffee_table": "coffee_table", "coffee table": "coffee_table", "side table": "coffee_table",
    "میز جلومبلی": "coffee_table", "میز جلو مبلی": "coffee_table", "میز عسلی": "coffee_table",
    "جلومبلی": "coffee_table", "عسلی": "coffee_table",
    "rug": "rug", "carpet": "rug", "فرش": "rug", "قالی": "rug", "قالیچه": "rug", "گلیم": "rug",
    # Basalam's own leaf titles (search hits carry ``categoryTitle``)
    "فرش دستباف": "rug", "فرش دستبافت": "rug", "فرش ماشینی": "rug", "فرش مدرن": "rug", "قالی دستباف": "rug",
    "lighting": "lighting", "lamp": "lighting", "chandelier": "lighting", "روشنایی": "lighting",
    "لوستر": "lighting", "آباژور": "lighting", "چراغ": "lighting", "چراغ ایستاده": "lighting",
    "چراغ رومیزی": "lighting", "چراغ آویز": "lighting",
    "chair": "chair", "armchair": "chair", "صندلی": "chair", "صندلی راحتی": "chair",
    "مبل تک نفره": "chair", "مبل تک‌نفره": "chair",
    "storage": "storage", "cabinet": "storage", "shelf": "storage", "bookcase": "storage",
    "sideboard": "storage", "tv stand": "storage", "بوفه": "storage", "ویترین": "storage",
    "شلف": "storage", "قفسه": "storage", "کتابخانه": "storage", "کمد": "storage", "شلف و استند": "storage",
    "میز تلویزیون": "storage", "کنسول": "storage", "دراور": "storage",
    "decor": "decor", "decoration": "decor", "دکور": "decor", "دکوری": "decor", "دکوراتیو": "decor",
    "کوسن": "decor", "بالش و کوسن": "decor", "تابلو": "decor", "آینه": "decor", "گلدان": "decor", "شمعدان": "decor",
    "مجسمه": "decor", "ساعت دیواری": "decor", "لوازم دکوری": "decor",
}


class RowRejected(ValueError):
    """The row cannot become a product; ``codes`` says why (stable identifiers).

    ``details`` are short, human-readable notes — *what* was seen for each
    failing field (``image_url=<missing> image_raw=photo={'MEDIUM': …}``) —
    so a report full of ``image_url_invalid`` explains itself without the
    raw dump. ``title_fa`` is carried so the report can still name the row.
    """

    def __init__(self, codes: list[str], details: list[str] | None = None, title_fa: str = ""):
        super().__init__(", ".join(codes))
        self.codes = codes
        self.details = list(details or [])
        self.title_fa = title_fa


@dataclass
class FeedRow:
    """One seller product, normalised. Field names mirror ``products`` columns."""

    source: str
    source_product_id: str
    title_fa: str
    category: str
    price_toman: int
    image_url: str
    seller_link: str = ""
    title_en: str = ""
    room_type: str = "living_room"
    width_cm: int = 0
    depth_cm: int = 0
    height_cm: int = 0
    colors: list[str] = field(default_factory=list)
    styles: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    description: str = ""
    #: When the seller price was observed. Defaults to the import moment —
    #: reading a live feed *is* the observation. A stale feed file should
    #: carry its own date so the gate can call the price stale.
    price_checked_at: datetime | None = None
    available: bool = True
    seller_name: str = ""
    #: Source excerpt kept on ``extraction_raw.import`` for provenance/debugging.
    raw: dict[str, Any] = field(default_factory=dict)
    #: Non-fatal normalisation notes (dropped tags, converted currency …).
    warnings: list[str] = field(default_factory=list)


# ----------------------------------------------------------------- primitives

def normalize_digits(value: str) -> str:
    """Persian/Arabic-Indic digits → ASCII."""
    return value.translate(_DIGIT_MAP)


def to_int(value: Any, *, allow_zero: bool = True) -> int | None:
    """Parse ``"۳۴٬۰۰۰٬۰۰۰"``, ``"34,000,000"``, ``34000000.0`` → ``34000000``.

    Returns ``None`` when the value is empty or not a number (never guesses).
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        number = int(round(value))
    else:
        text = _NUMBER_JUNK_RE.sub("", normalize_digits(str(value))).strip()
        if not text:
            return None
        # Strip a trailing unit the seller typed ("85 cm", "۳۴۰۰۰۰۰۰ تومان").
        text = re.sub(r"[^\d.\-]+$", "", text)
        try:
            number = int(round(float(text)))
        except ValueError:
            return None
    if number < 0 or (number == 0 and not allow_zero):
        return None
    return number


def to_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ("", "none", "null"):
        return default
    if text in ("1", "true", "yes", "y", "available", "in_stock", "موجود", "بله"):
        return True
    if text in ("0", "false", "no", "n", "unavailable", "out_of_stock", "ناموجود", "خیر"):
        return False
    return default


def split_list(value: Any) -> list[str]:
    """``"wood|metal"``, ``"wood, metal"``, ``["wood", "metal"]`` → ``["wood", "metal"]``."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items: Iterable[Any] = value
    else:
        items = _LIST_SPLIT_RE.split(str(value))
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in out:
            out.append(text)
    return out[:MAX_TAGS]


def parse_datetime(value: Any) -> datetime | None:
    """ISO-8601 (``Z`` accepted) → aware UTC datetime; ``None`` when absent/invalid."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = normalize_digits(str(value).strip())
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def map_category(value: Any, extra_aliases: Mapping[str, str] | None = None) -> str | None:
    """Seller category label → taxonomy id, or ``None`` when unmapped."""
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip().lower().replace("‌", " ").replace("ي", "ی").replace("ك", "ک")
    if not text:
        return None
    known = set(tax.categories())
    if text in known:
        return text
    table: dict[str, str] = {}
    for row in tax.taxonomy().get("categories", []):
        cid = row.get("id")
        if cid in known:
            for key in ("name_fa", "name_en"):
                if row.get(key):
                    table[str(row[key]).strip().lower()] = cid
    table.update({k.lower(): v for k, v in _CATEGORY_ALIASES.items() if v in known})
    if extra_aliases:
        table.update({str(k).strip().lower(): v for k, v in extra_aliases.items() if v in known})
    return table.get(text.replace("‌", " ")) or table.get(text)


def seller_source(slug: str) -> str:
    """``nilper`` → ``feed:nilper`` (validated; fits the 32-char column)."""
    slug = (slug or "").strip().lower()
    if not SELLER_SLUG_RE.match(slug):
        raise ValueError(
            f"seller slug {slug!r} must match {SELLER_SLUG_RE.pattern} "
            "(lowercase letters, digits, hyphens; max 26 chars)"
        )
    source = FEED_PREFIX + slug
    assert len(source) <= SOURCE_MAX_LEN
    return source


def parse_dimensions(value: Any) -> tuple[int, int, int] | None:
    """``"220x95x85"`` / ``"220 در 95 در 85"`` / ``{"length":..,"width":..,"height":..}``.

    Order follows the retail convention *length × width × height* → the
    product columns ``width_cm`` (footprint long side), ``depth_cm``,
    ``height_cm`` — the same mapping ``load_realistic_products`` uses.
    """
    if value is None or value == "":
        return None
    if isinstance(value, Mapping):
        length = to_int(value.get("length", value.get("width_cm")))
        width = to_int(value.get("width", value.get("depth_cm")))
        height = to_int(value.get("height", value.get("height_cm")))
        if length is None and width is None and height is None:
            return None
        return (length or 0, width or 0, height or 0)
    parts = [p for p in _DIMS_SPLIT_RE.split(normalize_digits(str(value))) if p.strip()]
    if len(parts) < 2:
        return None
    numbers = [to_int(p) for p in parts[:3]]
    if any(n is None for n in numbers):
        return None
    while len(numbers) < 3:
        numbers.append(0)
    return (numbers[0] or 0, numbers[1] or 0, numbers[2] or 0)


# ------------------------------------------------------------------ normaliser

def _clamp(values: list[str], kind: str, warnings: list[str]) -> list[str]:
    known, unknown = tax.clamp_to_taxonomy([v.strip().lower() for v in values], kind)
    if unknown:
        warnings.append(f"unknown_{kind}_dropped:{','.join(unknown)}")
    return known


def _colors(values: list[str], warnings: list[str]) -> list[str]:
    out: list[str] = []
    bad: list[str] = []
    for v in values:
        text = v.strip()
        if _HEX_RE.match(text):
            out.append(text.upper())
        else:
            bad.append(text)
    if bad:
        warnings.append(f"invalid_color_dropped:{','.join(bad)}")
    return out


def _url(value: Any, *, field_name: str, allow_local: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if allow_local and not text.startswith(("http://", "https://")):
        return text  # a local file path; the image step reads it from disk
    try:
        return validate_public_url(text, resolve=False, field=field_name)
    except UnsafeUrl:
        return None


def _url_problem(value: Any, *, field_name: str) -> str:
    """Why :func:`_url` said no, in one short phrase (for rejection details)."""
    text = str(value or "").strip()
    if not text:
        return "missing"
    try:
        validate_public_url(text, resolve=False, field=field_name)
    except UnsafeUrl as exc:
        return str(exc)[:120]
    return "ok"


def _short(value: Any, limit: int = 160) -> str:
    text = repr(value) if not isinstance(value, str) else value
    return text if len(text) <= limit else text[: limit - 1] + "…"


def normalize_row(
    raw: Mapping[str, Any],
    *,
    source: str,
    now: datetime | None = None,
    allow_local_images: bool = False,
    category_aliases: Mapping[str, str] | None = None,
    default_category: str | None = None,
) -> FeedRow:
    """Turn an adapter mapping into a :class:`FeedRow` or raise :class:`RowRejected`.

    Accepted keys (all optional unless stated): ``source_product_id`` *(required)*,
    ``title_fa`` *(required)*, ``title_en``/``title``, ``category`` *(required
    unless ``default_category``)*, ``price_toman`` *(required)* or ``price`` +
    ``currency`` (``toman``|``rial``), ``image_url`` *(required)*,
    ``seller_link``, ``width_cm``/``depth_cm``/``height_cm`` or
    ``dimensions_cm``, ``colors``, ``styles``, ``materials``, ``patterns``,
    ``description``, ``price_checked_at``, ``available``, ``seller_name``,
    ``room_type``.
    """
    codes: list[str] = []
    warnings: list[str] = []
    details: list[str] = []
    if not source or len(source) > SOURCE_MAX_LEN:
        raise RowRejected(["source_invalid"])

    spid = str(raw.get("source_product_id") or raw.get("id") or raw.get("sku") or "").strip()
    if not spid or len(spid) > SOURCE_PRODUCT_ID_MAX_LEN:
        codes.append("source_product_id_missing")

    title_fa = strip_html(str(raw.get("title_fa") or raw.get("name") or "")).strip()[:TITLE_MAX_LEN]
    if not title_fa:
        codes.append("title_fa_missing")
    title_en = strip_html(str(raw.get("title_en") or raw.get("title") or "")).strip()[:TITLE_MAX_LEN]

    category = map_category(raw.get("category"), category_aliases)
    if category is None and default_category in set(tax.categories()):
        category = default_category
    if category is None:
        codes.append("category_unmapped")
        details.append(f"category={_short(raw.get('category'), 60)!s}")

    price = to_int(raw.get("price_toman"), allow_zero=False)
    if price is None:
        base = to_int(raw.get("price"), allow_zero=False)
        currency = str(raw.get("currency") or "toman").strip().lower()
        if base is not None and currency in ("rial", "irr", "ریال"):
            price = base // 10
            warnings.append("price_converted_from_rial")
        else:
            price = base
    if price is None or price > MAX_PRICE_TOMAN:
        codes.append("price_invalid")
        details.append(f"price_toman={_short(raw.get('price_toman'), 40)} price={_short(raw.get('price'), 40)} "
                       f"currency={raw.get('currency') or 'toman'}")

    image_value = raw.get("image_url") or raw.get("image")
    image_url = _url(image_value, field_name="image_url", allow_local=allow_local_images)
    if image_url is None:
        codes.append("image_url_invalid")
        note = f"image_url={_url_problem(image_value, field_name='image_url')}"
        if not str(image_value or "").strip() and raw.get("image_raw"):
            note += f" image_raw={_short(raw.get('image_raw'))}"
        elif str(image_value or "").strip():
            note += f" value={_short(image_value, 120)}"
        details.append(note)

    seller_link = ""
    raw_link = raw.get("seller_link") or raw.get("url") or raw.get("product_url")
    if raw_link:
        checked = _url(raw_link, field_name="seller_link")
        if checked is None:
            warnings.append("seller_link_invalid_dropped")
        else:
            seller_link = checked

    dims = parse_dimensions(raw.get("dimensions_cm") or raw.get("dimensions"))
    if dims is None:
        dims = (to_int(raw.get("width_cm")) or 0, to_int(raw.get("depth_cm")) or 0,
                to_int(raw.get("height_cm")) or 0)
    if any(d > MAX_DIMENSION_CM for d in dims):
        codes.append("dimensions_invalid")

    colors = _colors(split_list(raw.get("colors") or raw.get("color_palette")), warnings)
    styles = _clamp(split_list(raw.get("styles") or raw.get("style_tags")), "style", warnings)
    materials = _clamp(split_list(raw.get("materials") or raw.get("material_tags")), "material", warnings)
    patterns = _clamp(split_list(raw.get("patterns") or raw.get("pattern_tags")), "pattern", warnings)

    description = strip_html(
        str(raw.get("description") or raw.get("description_for_embedding") or raw.get("summary") or "")
    )[:DESCRIPTION_MAX_LEN]

    checked_at = parse_datetime(raw.get("price_checked_at"))
    if raw.get("price_checked_at") and checked_at is None:
        warnings.append("price_checked_at_unparseable_defaulted_to_now")
    if checked_at is None:
        checked_at = now or datetime.now(timezone.utc)

    room_type = str(raw.get("room_type") or "living_room").strip() or "living_room"

    if codes:
        raise RowRejected(codes, details, title_fa=title_fa)
    assert category is not None and price is not None and image_url is not None

    return FeedRow(
        source=source,
        source_product_id=spid,
        title_fa=title_fa,
        title_en=title_en,
        category=category,
        room_type=room_type,
        price_toman=price,
        image_url=image_url,
        seller_link=seller_link,
        width_cm=dims[0],
        depth_cm=dims[1],
        height_cm=dims[2],
        colors=colors,
        styles=styles,
        materials=materials,
        patterns=patterns,
        description=description,
        price_checked_at=checked_at,
        available=to_bool(raw.get("available"), default=True),
        seller_name=strip_html(str(raw.get("seller_name") or ""))[:120],
        raw=dict(raw),
        warnings=warnings,
    )
