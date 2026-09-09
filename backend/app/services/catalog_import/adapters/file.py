"""CSV / JSON seller feed → rows for the importer.

The file contract is the documented template ``seed_data/feed_template.csv``
(one header row, UTF-8, a BOM is tolerated because Excel writes one). Column
names are the ``FeedRow`` field names; a small alias table accepts the Persian
headers a shop assistant would type (``عنوان``, ``دسته``, ``قیمت`` …) and the
column names of the repo's own realistic dataset (``title_fa``, ``style_tags``,
``material_tags``, ``color_palette``, ``dimensions_cm``) so the same importer
handles both.

JSON accepts either a top-level list or ``{"items": [...]}``; per-row keys
follow the same aliases.
"""
from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

#: header alias → canonical key (canonical keys are what normalize_row reads)
HEADER_ALIASES: dict[str, str] = {
    "id": "source_product_id", "sku": "source_product_id", "product_id": "source_product_id",
    "کد": "source_product_id", "کد محصول": "source_product_id", "شناسه": "source_product_id",
    "title_fa": "title_fa", "name": "title_fa", "عنوان": "title_fa", "نام": "title_fa",
    "نام محصول": "title_fa", "عنوان محصول": "title_fa",
    "title_en": "title_en", "title": "title_en", "عنوان انگلیسی": "title_en",
    "category": "category", "دسته": "category", "دسته‌بندی": "category", "دسته بندی": "category",
    "price_toman": "price_toman", "price": "price", "قیمت": "price_toman", "قیمت (تومان)": "price_toman",
    "قیمت تومان": "price_toman", "قیمت (ریال)": "price_rial",
    "currency": "currency", "واحد پول": "currency",
    "image_url": "image_url", "image": "image_url", "photo": "image_url", "تصویر": "image_url",
    "لینک تصویر": "image_url", "عکس": "image_url",
    "seller_link": "seller_link", "url": "seller_link", "product_url": "seller_link", "link": "seller_link",
    "لینک": "seller_link", "لینک محصول": "seller_link", "لینک خرید": "seller_link",
    "width_cm": "width_cm", "length_cm": "width_cm", "طول": "width_cm", "طول (سانتی‌متر)": "width_cm",
    "depth_cm": "depth_cm", "عرض": "depth_cm", "عرض (سانتی‌متر)": "depth_cm", "عمق": "depth_cm",
    "height_cm": "height_cm", "ارتفاع": "height_cm", "ارتفاع (سانتی‌متر)": "height_cm",
    "dimensions_cm": "dimensions_cm", "dimensions": "dimensions_cm", "ابعاد": "dimensions_cm",
    "ابعاد (سانتی‌متر)": "dimensions_cm",
    "colors": "colors", "color_palette": "colors", "رنگ": "colors", "رنگ‌ها": "colors",
    "styles": "styles", "style_tags": "styles", "سبک": "styles",
    "materials": "materials", "material_tags": "materials", "جنس": "materials", "متریال": "materials",
    "patterns": "patterns", "pattern_tags": "patterns", "طرح": "patterns",
    "description": "description", "description_for_embedding": "description", "توضیحات": "description",
    "price_checked_at": "price_checked_at", "تاریخ قیمت": "price_checked_at",
    "available": "available", "in_stock": "available", "stock": "available", "موجودی": "available",
    "موجود": "available",
    "seller_name": "seller_name", "seller": "seller_name", "فروشنده": "seller_name",
    "room_type": "room_type",
}

#: The documented CSV template (also written by ``scripts/import_catalog.py --template``).
TEMPLATE_COLUMNS = [
    "source_product_id", "title_fa", "title_en", "category", "price_toman", "price_checked_at",
    "image_url", "seller_link", "width_cm", "depth_cm", "height_cm", "colors", "styles",
    "materials", "patterns", "description", "available", "seller_name",
]


def _canon(header: str) -> str:
    key = header.strip().lstrip("\ufeff").strip().lower()
    key = key.replace("ي", "ی").replace("ك", "ک")
    return HEADER_ALIASES.get(key, key)


def _canon_row(row: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        ck = _canon(str(key))
        if ck == "price_rial":
            out.setdefault("price", value)
            out["currency"] = "rial"
            continue
        if isinstance(value, str):
            value = value.strip()
        if value in ("", None) and ck in out:
            continue
        out[ck] = value
    return out


def iter_csv(text: str) -> Iterator[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    for row in reader:
        if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
            continue  # blank line
        yield _canon_row(row)


def iter_json(text: str) -> Iterator[dict[str, Any]]:
    data = json.loads(text)
    rows = data.get("items") if isinstance(data, Mapping) else data
    if not isinstance(rows, list):
        raise ValueError("JSON feed must be a list of objects or {\"items\": [...]}")
    for row in rows:
        if isinstance(row, Mapping):
            yield _canon_row(row)


def iter_file(path: str | Path) -> Iterator[dict[str, Any]]:
    """Dispatch on suffix: ``.csv`` / ``.json`` (``.jsonl`` = one object per line)."""
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig")
    suffix = p.suffix.lower()
    if suffix == ".csv":
        yield from iter_csv(text)
    elif suffix == ".json":
        yield from iter_json(text)
    elif suffix == ".jsonl":
        for line in text.splitlines():
            if line.strip():
                yield _canon_row(json.loads(line))
    else:
        raise ValueError(f"unsupported feed file type {suffix!r} (use .csv, .json or .jsonl)")


def template_csv() -> str:
    """Header + one worked example row (Persian digits are accepted on import)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(TEMPLATE_COLUMNS)
    writer.writerow([
        "NLP-1042", "مبل راحتی سه‌نفره مدل آرتا", "Arta 3-seat sofa", "مبل", "48500000",
        "2026-09-09", "https://cdn.example-seller.ir/products/arta-3-seat.jpg",
        "https://example-seller.ir/product/arta-3-seat-sofa", "215", "92", "84",
        "#C9B79C|#3B3B3B", "modern|minimal", "fabric|wood", "solid",
        "مبل سه‌نفره با پارچه کتان و پایه چوب راش", "true", "Example Seller",
    ])
    return buf.getvalue()
