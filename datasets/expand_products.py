#!/usr/bin/env python3
"""Deterministically expand the curated 20-product sample to a balanced catalog.

This does not invent seller URLs: variants retain their source product's retailer
page and image while varying catalog-facing title, price, dimensions and palette.
It is demo data, not a live retailer feed; replace it with the client's export in
production.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import random
from collections import Counter
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "products_realistic.json"
DEFAULT_OUTPUT = ROOT / "products_realistic_150.json"
TARGETS = {
    "sofa": 30,
    "coffee_table": 20,
    "rug": 20,
    "lighting": 20,
    "chair": 20,
    "storage": 20,
    "decor": 20,
}
ADJECTIVES_FA = ["ویژه", "آرکا", "چستر", "راحتی", "دکوراتیو", "آرتا", "سپید", "هیراد"]


def shift_color(value: str, amount: float) -> str:
    r, g, b = (int(value[i : i + 2], 16) / 255 for i in (1, 3, 5))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    r, g, b = colorsys.hsv_to_rgb((h + amount) % 1, min(1, s * 1.02), min(1, v * 1.01))
    return f"#{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"


def expand(source: list[dict], targets: dict[str, int] = TARGETS) -> list[dict]:
    rng = random.Random(1403)
    by_category: dict[str, list[dict]] = {category: [] for category in targets}
    aliases = {"armchair": "chair", "tv_stand": "storage", "bookshelf": "storage", "curtain": "decor"}
    for product in source:
        category = aliases.get(product["category"], product["category"])
        if category in by_category:
            normalized = deepcopy(product)
            normalized["category"] = category
            by_category[category].append(normalized)

    # Sparse categories borrow semantically close products, but keep realistic
    # dimensions, images and seller URLs from a curated source row.
    fallback = {
        "chair": by_category["sofa"],
        "storage": by_category["coffee_table"],
        "decor": by_category["rug"] + by_category["lighting"],
    }
    result: list[dict] = []
    serial = 1
    for category, target in targets.items():
        pool = by_category[category] or fallback.get(category) or source
        for index in range(target):
            base = deepcopy(pool[index % len(pool)])
            variant = index // len(pool)
            base["id"] = f"real_{serial:03d}"
            base["category"] = category
            if variant:
                price_factor = 1 + rng.uniform(-0.10, 0.10)
                base["title_fa"] = f"{base['title_fa']} مدل {ADJECTIVES_FA[(variant + index) % len(ADJECTIVES_FA)]}"
                base["title_en"] = f"{base.get('title_en', category.title())} Variant {variant + 1}"
                base["price_toman"] = max(100_000, int(round(base["price_toman"] * price_factor, -4)))
                for key, value in base["dimensions_cm"].items():
                    base["dimensions_cm"][key] = max(1, round(value * (1 + rng.uniform(-0.05, 0.05))))
                base["color_palette"] = [shift_color(c, rng.uniform(-0.012, 0.012)) for c in base["color_palette"]]
                base["description_for_embedding"] += f" {category.replace('_', ' ')} catalog variant {variant + 1}"
            base["dataset_notice"] = "Synthetic catalog variation of a curated sample; verify price and availability with seller."
            result.append(base)
            serial += 1
    assert len(result) == sum(targets.values())
    assert Counter(p["category"] for p in result) == Counter(targets)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    products = expand(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(products, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(products)} products to {args.output}")
    print(dict(Counter(p["category"] for p in products)))


if __name__ == "__main__":
    main()
