#!/usr/bin/env python3
"""Convert an internal catalog JSON file into the client-facing catalog CSV.

Stage 4 / T-4.6. Two uses:

1. **Reproducibility.** The T-4.6 evidence claims `scripts/validate_catalog.py`
   accepts the real 150-product catalog. That claim is only checkable if the
   JSON -> CSV mapping used for the cross-check is committed rather than
   improvised, so this file *is* that mapping:

       python scripts/catalog_json_to_csv.py \\
           backend/seed_data/products_realistic_150.json /tmp/real150.csv
       python scripts/validate_catalog.py /tmp/real150.csv     # expect EXIT=0

2. **Client migration.** A client whose catalog is already JSON can convert it
   to the reviewable CSV instead of retyping it in Excel.

Mapping rules (documented in docs/client/CATALOG_SPEC.fa.md §تبدیل از JSON):

    dimensions_cm  {"length":220,"width":95,"height":85}  ->  "220x95x85"
    color_palette  ["#CFCFD1","#2E2E2E"]                  ->  "#CFCFD1,#2E2E2E"
    style_tags     ["modern","minimal"]                   ->  "modern,minimal"
    material_tags  ["fabric","metal"]                     ->  "fabric,metal"
    everything else                                       ->  written verbatim
    dataset_notice and any other extra key                ->  dropped

`dataset_notice` is intentionally dropped: it is an internal provenance note
about synthetic seed data, not a product attribute, and the client catalog has
no column for it. Output is UTF-8 **with BOM** so Excel opens the Persian text
correctly — the same reason validate_catalog.py reads with utf-8-sig.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# Kept in the same order as CATALOG_SPEC.fa.md and catalog-template.csv.
COLUMNS = [
    "id",
    "title_fa",
    "title_en",
    "category",
    "room_type",
    "price_toman",
    "seller",
    "seller_link",
    "image_url",
    "dimensions_cm",
    "color_palette",
    "style_tags",
    "material_tags",
    "description_for_embedding",
]

LIST_COLUMNS = {"color_palette", "style_tags", "material_tags"}


def format_dimensions(value: object) -> str:
    """{'length': 220, 'width': 95, 'height': 85} -> '220x95x85'."""
    if isinstance(value, dict):
        try:
            return "x".join(str(value[k]) for k in ("length", "width", "height"))
        except KeyError as exc:
            raise ValueError(f"dimensions_cm is missing key {exc}") from exc
    return str(value or "")


def to_row(record: dict) -> dict[str, str]:
    row: dict[str, str] = {}
    for column in COLUMNS:
        value = record.get(column, "")
        if column == "dimensions_cm":
            row[column] = format_dimensions(value)
        elif column in LIST_COLUMNS and isinstance(value, list):
            row[column] = ",".join(str(v) for v in value)
        else:
            row[column] = "" if value is None else str(value)
    return row


def convert(src: Path, dest: Path) -> int:
    data = json.loads(src.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        # Tolerate {"products": [...]} as well as a bare list.
        for key in ("products", "items", "catalog"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            raise ValueError("JSON object has no products/items/catalog list")
    if not isinstance(data, list):
        raise ValueError("expected a JSON list of product objects")

    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for index, record in enumerate(data):
            if not isinstance(record, dict):
                raise ValueError(f"item {index} is not an object")
            writer.writerow(to_row(record))
    return len(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert internal catalog JSON to the client-facing catalog CSV."
    )
    parser.add_argument("json_path", type=Path, help="source JSON catalog")
    parser.add_argument("csv_path", type=Path, help="destination CSV")
    args = parser.parse_args(argv)

    try:
        count = convert(args.json_path, args.csv_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"conversion failed: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {count} rows -> {args.csv_path}")
    print(f"now validate it:  python scripts/validate_catalog.py {args.csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
