"""Catalog-integrity policy — the rules that decide whether a product row is
*true enough* to be recommended (ADR-016).

Why this module exists
----------------------
The engine can only be as honest as its rows. The 2026-09-07 live probe found a
"rug" whose image was a living-room sofa, whose materials were ``metal`` and
``leather`` and whose seller link was the marketplace home page. Nothing in the
pipeline could have caught it: the vision prompt did not emit a category, the
review gate only looked at confidence, and the seller-link check only asked
"does the host answer". This module is the missing contract between the data
and the recommender: a small, versioned, *pure* set of checks that every
ingestion path (seed scripts, importer, admin upload/verify, CI audit) runs and
that the recommender enforces at query time (``integrity_ok IS NOT FALSE``).

Two tiers, on purpose
---------------------
* ``ALWAYS_BLOCKING`` — the row is *wrong*: the picture shows another category,
  a rug made of metal, a 9 m sofa, an English template string where the
  Persian title should be, a seller link that is dead or unsafe. Wrong rows are
  refused in every environment.
* ``PRODUCTION_BLOCKING`` — the row is *not sellable yet*: synthetic demo data,
  a duplicate photo, no seller link or a shallow one, an unchecked/stale price,
  a missing Persian title. Development and CI catalogs are allowed to be
  synthetic; a production catalog is not. These fire only when
  ``strict=True`` (the default in ``APP_ENV=production``); elsewhere they are
  returned as *advisories* so operators can see how far the catalog is from
  shippable.

Everything here is a pure function over a product-like object (ORM row, dict,
or importer record) so the same decision can be replayed in tests, in the CI
audit and against a stored row. Codes are stable identifiers; the texts are
for operators and the admin UI.
"""
from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from ai import taxonomy as tax

INTEGRITY_POLICY_VERSION = "2026-09-07.1"

#: Rows from these sources are demo/benchmark data, never inventory.
SYNTHETIC_SOURCES = frozenset({"synthetic-demo", "perf"})

#: A price older than this (or never checked) is not a price a shopper can act on.
PRICE_MAX_AGE_DAYS = 30

ALWAYS_BLOCKING = frozenset({
    "image_category_mismatch",
    "image_unreachable",
    "material_implausible",
    "dimensions_out_of_band",
    "title_fa_invalid",
    "seller_link_dead",
    "category_unknown",
})

PRODUCTION_BLOCKING = frozenset({
    "synthetic_row",
    "duplicate_image",
    "seller_link_missing",
    "seller_link_shallow",
    "price_stale",
    "price_out_of_band",
    "title_fa_missing",
})

ALL_CODES = ALWAYS_BLOCKING | PRODUCTION_BLOCKING

#: Marker appended to ``integrity_reasons`` when an admin verified a failing
#: row with ``?force=true`` (audited). It is not a check and never blocks.
ADMIN_OVERRIDE = "admin_override"

INTEGRITY_REASON_TEXT: dict[str, dict[str, str]] = {
    "image_category_mismatch": {
        "en": "the image shows a different product category than the row claims",
        "fa": "تصویر محصول با دسته‌بندی ثبت‌شده هم‌خوانی ندارد",
    },
    "image_unreachable": {
        "en": "the image URL does not answer 2xx",
        "fa": "تصویر محصول در دسترس نیست",
    },
    "material_implausible": {
        "en": "a listed material is implausible for this category (e.g. a metal rug)",
        "fa": "متریال ثبت‌شده برای این دسته منطقی نیست (مثلاً فرش فلزی)",
    },
    "dimensions_out_of_band": {
        "en": "declared dimensions are outside the plausible band for the category",
        "fa": "ابعاد ثبت‌شده خارج از بازهٔ منطقی این دسته است",
    },
    "title_fa_invalid": {
        "en": "the Persian title has no Persian letters, or an English taxonomy word appears without a model marker (مدل/طرح/سری/کد/برند)",
        "fa": "عنوان فارسی حرف فارسی ندارد یا واژهٔ انگلیسی تاکسونومی بدون نشانگر مدل (مدل/طرح/سری/کد/برند) دارد",
    },
    "seller_link_dead": {
        "en": "the seller link was last checked dead or unsafe",
        "fa": "لینک فروشنده در آخرین بررسی مرده یا ناامن بود",
    },
    "category_unknown": {
        "en": "the category is not in the catalog taxonomy",
        "fa": "دسته‌بندی در تاکسونومی کاتالوگ وجود ندارد",
    },
    "synthetic_row": {
        "en": "demo/benchmark row, not inventory (source is synthetic)",
        "fa": "ردیف نمونه/آزمایشی است، نه موجودی واقعی",
    },
    "duplicate_image": {
        "en": "another product uses the same image",
        "fa": "محصول دیگری همین تصویر را دارد",
    },
    "seller_link_missing": {
        "en": "no seller link — the product cannot be bought from the card",
        "fa": "لینک فروشنده ندارد — از روی کارت قابل خرید نیست",
    },
    "seller_link_shallow": {
        "en": "seller link points at a home/category/search page, not the product",
        "fa": "لینک فروشنده به صفحهٔ اصلی/دسته/جست‌وجو اشاره می‌کند، نه صفحهٔ محصول",
    },
    "price_stale": {
        "en": f"price never checked or older than {PRICE_MAX_AGE_DAYS} days",
        "fa": f"قیمت بررسی نشده یا قدیمی‌تر از {PRICE_MAX_AGE_DAYS} روز است",
    },
    "price_out_of_band": {
        "en": "price is outside the plausible band for the category",
        "fa": "قیمت خارج از بازهٔ منطقی این دسته است",
    },
    "title_fa_missing": {
        "en": "no Persian title",
        "fa": "عنوان فارسی ندارد",
    },
    ADMIN_OVERRIDE: {
        "en": "an admin verified this row despite failing checks (audited)",
        "fa": "ادمین با وجود خطاهای بررسی، این ردیف را تأیید کرده است (ثبت در لاگ)",
    },
}

# ---------------------------------------------------------------------------
# Per-category plausibility tables. Coarse by design: the taxonomy has six
# materials and seven categories, so these are "cannot be" lists, not
# engineering specs. An admin can still ``force`` a legitimate outlier.
# ---------------------------------------------------------------------------
PLAUSIBLE_MATERIALS: dict[str, frozenset[str]] = {
    "sofa": frozenset({"fabric", "leather", "wood", "metal", "rattan"}),
    "coffee_table": frozenset({"wood", "metal", "glass", "rattan"}),
    "rug": frozenset({"fabric", "leather"}),
    "lighting": frozenset({"metal", "glass", "wood", "fabric", "rattan"}),
    "chair": frozenset({"wood", "metal", "fabric", "leather", "rattan"}),
    "storage": frozenset({"wood", "metal", "glass", "rattan"}),
    "decor": frozenset({"wood", "metal", "fabric", "leather", "glass", "rattan"}),
}

#: (min, max) centimetres for width_cm / depth_cm / height_cm. A value of 0 or
#: None means "unknown" and is not checked (the fit score treats it the same).
DIMENSION_BANDS: dict[str, tuple[tuple[int, int], tuple[int, int], tuple[int, int]]] = {
    "sofa": ((100, 450), (50, 200), (40, 130)),
    "coffee_table": ((30, 250), (20, 150), (15, 80)),
    "rug": ((40, 600), (40, 600), (0, 6)),
    "lighting": ((3, 200), (3, 200), (5, 300)),
    "chair": ((30, 150), (30, 150), (30, 150)),
    "storage": ((15, 400), (10, 120), (10, 300)),
    "decor": ((1, 300), (1, 300), (1, 300)),
}

#: Toman. Wide on purpose — this catches 1-toman drafts and lost zeros, not
#: market pricing. Revisit once a real seller feed is imported (P4-ب).
PRICE_BANDS_TOMAN: dict[str, tuple[int, int]] = {
    "sofa": (5_000_000, 2_000_000_000),
    "coffee_table": (1_000_000, 500_000_000),
    "rug": (1_000_000, 3_000_000_000),
    "lighting": (300_000, 500_000_000),
    "chair": (1_000_000, 500_000_000),
    "storage": (1_000_000, 800_000_000),
    "decor": (100_000, 200_000_000),
}

#: Path prefixes that mean "a listing page", not "this product".
_SHALLOW_PATH_RE = re.compile(
    r"^/(main|search|browse|list|catalog|catalogue|category|categories|c|s|brand|brands"
    r"|seller|shop|store|tag|tags|collections?)(/|$)",
    re.IGNORECASE,
)

_PERSIAN_LETTER_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")


def _latin_taxonomy_word_re() -> re.Pattern[str]:
    words = set(tax.styles()) | set(tax.materials()) | set(tax.categories()) | {
        "sofa", "rug", "lamp", "chair", "table", "shelf", "cushion", "decor",
    }
    # ``coffee_table`` -> also match "coffee table"
    alts = sorted({w.replace("_", " ") for w in words} | words, key=len, reverse=True)
    return re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(a) for a in alts) + r")(?![A-Za-z])", re.IGNORECASE)


_LATIN_TAXONOMY_WORD_RE = _latin_taxonomy_word_re()
# A Latin taxonomy word is legitimate in a Persian title only as a *model
# name*: «مبل راحتی مدل Modern». Bare, it is a template artefact («فرش modern»).
_MODEL_MARKER_RE = re.compile(r"(?:^|\s)(?:مدل|طرح|سری|کد|برند)\s*$")


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def image_key(image_url: str | None, image_phash: str | None = None) -> str | None:
    """Stable identity of a product image for duplicate detection.

    A perceptual hash wins when present (two uploads of the same bytes get
    different storage keys); otherwise the URL without its query string, so
    ``?w=800`` and ``?w=1200`` of the same CDN photo collide as they should.
    """
    if image_phash:
        return f"phash:{str(image_phash).lower()}"
    if not image_url:
        return None
    parts = urlsplit(str(image_url).strip())
    host = (parts.hostname or "").lower()
    return f"url:{host}{parts.path}"


def seller_link_depth(url: str | None) -> str:
    """``"missing"`` | ``"shallow"`` | ``"deep"``."""
    if not url or not str(url).strip():
        return "missing"
    parts = urlsplit(str(url).strip())
    path = parts.path or "/"
    if path in ("", "/"):
        return "shallow"
    if _SHALLOW_PATH_RE.match(path):
        return "shallow"
    return "deep"


def title_fa_problem(title_fa: str | None) -> str | None:
    """``None`` when fine, else ``"title_fa_missing"`` / ``"title_fa_invalid"``.

    Invalid means *not a Persian product title*: no Persian letters at all, or
    a template artefact — an English taxonomy token («modern», «sofa», …) that
    is not introduced by a model marker (مدل/طرح/سری/کد/برند). The live bug was
    «فرش modern»; real listings legitimately carry Latin model names
    («مبل راحتی مدل Modern») and stay valid.
    """
    text = (title_fa or "").strip()
    if not text:
        return "title_fa_missing"
    if not _PERSIAN_LETTER_RE.search(text):
        return "title_fa_invalid"
    for match in _LATIN_TAXONOMY_WORD_RE.finditer(text):
        if not _MODEL_MARKER_RE.search(text[: match.start()]):
            return "title_fa_invalid"
    return None


def detected_category_of(product: Any) -> str | None:
    """The category the vision model saw (``extraction_raw.detected_category``)."""
    raw = _get(product, "extraction_raw") or {}
    if not isinstance(raw, Mapping):
        return None
    value = raw.get("detected_category")
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value or None


def is_synthetic(product: Any) -> bool:
    source = (_get(product, "source") or "").strip().lower()
    if source in SYNTHETIC_SOURCES:
        return True
    raw = _get(product, "extraction_raw") or {}
    if isinstance(raw, Mapping):
        raw_source = str(raw.get("source") or "").lower()
        if raw_source in SYNTHETIC_SOURCES or raw_source.startswith("realistic_dataset"):
            return True
        if raw.get("dataset_notice"):
            return True
    return False


def integrity_checks(
    product: Any,
    *,
    known_images: Mapping[str, Collection[str]] | None = None,
    now: datetime | None = None,
    observed: Iterable[str] = (),
) -> list[str]:
    """Return every failing check code for ``product`` (both tiers, unordered by
    tier, deterministic order). ``known_images`` maps :func:`image_key` to the
    ids of products carrying that image (may include this product's own id).
    ``observed`` folds in failures only an external probe can see
    (``image_unreachable`` from the audit script)."""
    codes: list[str] = []
    category = str(_get(product, "category") or "").strip()
    pid = str(_get(product, "id") or "")

    if category not in tax.categories():
        codes.append("category_unknown")

    detected = detected_category_of(product)
    if detected and detected in tax.categories() and category and detected != category:
        codes.append("image_category_mismatch")

    materials = _get(product, "materials") or []
    allowed = PLAUSIBLE_MATERIALS.get(category)
    if allowed is not None and isinstance(materials, (list, tuple, set)):
        listed = {str(m).strip().lower() for m in materials if str(m).strip()}
        if listed and not listed <= allowed:
            codes.append("material_implausible")

    bands = DIMENSION_BANDS.get(category)
    if bands is not None:
        dims = (_int(_get(product, "width_cm")), _int(_get(product, "depth_cm")), _int(_get(product, "height_cm")))
        for value, (lo, hi) in zip(dims, bands, strict=True):
            if value and not (lo <= value <= hi):
                codes.append("dimensions_out_of_band")
                break

    title_problem = title_fa_problem(_get(product, "title_fa"))
    if title_problem:
        codes.append(title_problem)

    link = _get(product, "seller_link") or ""
    depth = seller_link_depth(link)
    if depth == "missing":
        codes.append("seller_link_missing")
    elif depth == "shallow":
        codes.append("seller_link_shallow")
    status = str(_get(product, "link_status") or "").lower()
    if link and status in ("dead", "unsafe"):
        codes.append("seller_link_dead")

    if is_synthetic(product):
        codes.append("synthetic_row")

    key = image_key(_get(product, "image_url"), _get(product, "image_phash"))
    if key and known_images:
        others = {str(i) for i in known_images.get(key, ())} - ({pid} if pid else set())
        if others:
            codes.append("duplicate_image")

    price = _int(_get(product, "price_toman"))
    band = PRICE_BANDS_TOMAN.get(category)
    if band is not None and price and not (band[0] <= price <= band[1]):
        codes.append("price_out_of_band")

    checked = _get(product, "price_checked_at")
    ref = now or datetime.now(timezone.utc)
    if not isinstance(checked, datetime):
        codes.append("price_stale")
    else:
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        if ref - checked > timedelta(days=PRICE_MAX_AGE_DAYS):
            codes.append("price_stale")

    for code in observed:
        if code in ALL_CODES and code not in codes:
            codes.append(code)

    order = {code: i for i, code in enumerate(sorted(ALL_CODES))}
    return sorted(dict.fromkeys(codes), key=lambda c: order.get(c, 99))


def integrity_decision(
    product: Any,
    *,
    strict: bool = False,
    known_images: Mapping[str, Collection[str]] | None = None,
    now: datetime | None = None,
    observed: Iterable[str] = (),
) -> dict[str, Any]:
    """``{"ok", "reasons", "advisories", "checks", "strict", "policy_version"}``.

    ``reasons`` are the codes that block under the current mode; ``advisories``
    are production-only codes reported in non-strict mode. ``checks`` is the
    union (what the row would need to fix to be shippable).
    """
    checks = integrity_checks(product, known_images=known_images, now=now, observed=observed)
    blocking_set = ALL_CODES if strict else ALWAYS_BLOCKING
    reasons = [c for c in checks if c in blocking_set]
    advisories = [c for c in checks if c not in blocking_set]
    return {
        "ok": not reasons,
        "reasons": reasons,
        "advisories": advisories,
        "checks": checks,
        "strict": bool(strict),
        "policy_version": INTEGRITY_POLICY_VERSION,
    }


def describe(codes: Iterable[str], lang: str = "en") -> list[str]:
    """Human-readable lines for a list of codes (unknown codes echoed verbatim)."""
    out = []
    for code in codes:
        text = INTEGRITY_REASON_TEXT.get(code, {}).get(lang)
        out.append(f"{code}: {text}" if text else code)
    return out
