#!/usr/bin/env python
"""Seed a deterministic synthetic catalog at realistic scale (pgvector bench).

Master Prompt 04 work item 8: "Test pgvector query plans and p95 using
realistic catalog sizes (at least 1k and synthetic 10k)". The dev catalog has
100-150 rows — far too small for the planner to ever prefer the HNSW index.

Rows are prefixed ``scale-{size}-{n}`` (plus ``--prefix``) so a bench run can
be removed cleanly:

    DELETE FROM products WHERE id LIKE 'scale-%';

Determinism: seeded PRNG per (size) — same catalog on every machine. Titles
are composed from Persian word banks so the data *looks* like a real Persian
catalog (and exercises UTF-8 paths); embeddings use the deterministic hash
backend so the run is hermetic. Hash vectors are **not** CLIP geometry — the
benchmark measures index/planner/latency behaviour, not semantic quality
(see docs/ai/evaluation-report.md §limitations).

Usage:
    DATABASE_URL=postgres://... python scripts/seed_catalog_scale.py --rows 1000
    DATABASE_URL=postgres://... python scripts/seed_catalog_scale.py --rows 10000
    DATABASE_URL=postgres://... python scripts/seed_catalog_scale.py --clear --rows 10000
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, func, select, text  # noqa: E402

from ai.embedding_service import get_embedding, product_to_text  # noqa: E402
from ai.taxonomy import materials as TAX_MATERIALS  # noqa: E402
from ai.taxonomy import patterns as TAX_PATTERNS  # noqa: E402
from ai.taxonomy import styles as TAX_STYLES  # noqa: E402
from app.models import Product  # noqa: E402

TITLE_FA = {
    "sofa": ["مبل راحتی", "مبل گوشواره", "کاناپه", "مبل تختخواب‌شو"],
    "coffee_table": ["میز جلومبلی", "میز چای", "میز عسلی"],
    "rug": ["فرش ماشینی", "فرش دست‌بافت", "قالیچه", "روفرشی"],
    "lighting": ["چراغ آویز", "آباژور", "لوستر", "چراغ ایستاده"],
    "chair": ["صندلی راحتی", "مبل تک", "صندلی غذاخوری"],
    "storage": ["میز تلویزیون", "کتابخانه", "کمد نمایشی", "کنسول"],
    "decor": ["پرده", "آینه دکوراتیو", "تابلو", "گلدان"],
}
ADJECTIVES_FA = ["مدرن", "کلاسیک", "اسکاندیناوی", "دست‌ساز", "لوکس", "ساده", "چرمی", "چوبی"]

PRICE_BANDS = {
    "sofa": (18_000_000, 120_000_000), "coffee_table": (3_000_000, 30_000_000),
    "rug": (5_000_000, 80_000_000), "lighting": (1_500_000, 25_000_000),
    "chair": (8_000_000, 45_000_000), "storage": (6_000_000, 40_000_000),
    "decor": (2_000_000, 18_000_000),
}
CATEGORIES = list(TITLE_FA)


def build_rows(target: int, size_tag: str) -> list[Product]:
    rng = random.Random(20260821 + int(size_tag))
    products: list[Product] = []
    for i in range(target):
        category = CATEGORIES[i % len(CATEGORIES)]
        style = rng.choice(TAX_STYLES())
        mats = rng.sample(TAX_MATERIALS(), k=rng.choice([1, 2]))
        pattern = rng.choice(TAX_PATTERNS()) if category in ("rug", "decor") else "solid"
        lo, hi = PRICE_BANDS[category]
        price = int(round(rng.uniform(lo, hi), -5))
        base = rng.choice(TITLE_FA[category])
        adj = rng.choice(ADJECTIVES_FA)
        title = f"{adj} {base} {style} {i}"  # unique + persian components
        title_fa = f"{adj} {base}"
        description = f"a {style} {category.replace('_', ' ')} made of {' and '.join(mats)}"
        emb = get_embedding(product_to_text(title, [style], ["#888888"], mats, description, [pattern]))
        products.append(Product(
            id=f"scale-{size_tag}-{i:06d}",
            title=title,
            title_fa=title_fa,
            category=category,
            room_type="living_room",
            price_toman=price,
            image_url=f"https://images.example.com/scale/{size_tag}/{i}.jpg",
            seller_link="https://example.com/seller",
            seller_link_ok=True,
            colors=["#888888"],
            styles=[style],
            materials=mats,
            patterns=[pattern],
            width_cm=rng.randint(60, 260), depth_cm=rng.randint(30, 100),
            height_cm=rng.randint(2, 220),
            description=description,
            extraction_confidence=round(rng.uniform(0.82, 0.97), 2),
            is_verified=(rng.random() > 0.15),
            style_embedding=emb,
        ))
    return products


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1000)
    ap.add_argument("--clear", action="store_true", help="delete scale-* rows first")
    ap.add_argument("--prefix", default="scale")
    args = ap.parse_args()

    from app.core.config import settings

    if not settings.is_postgres:
        print("ERROR: this seeder targets the PostgreSQL/pgvector path "
              f"(DATABASE_URL={settings.DATABASE_URL!r} is not postgres)")
        return 2

    engine = create_engine(settings.DATABASE_URL)
    size_tag = str(args.rows)
    Product.metadata.create_all(engine)
    with engine.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        c.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_products_style_embedding ON products "
            "USING hnsw (style_embedding vector_cosine_ops)"
        ))
        if args.clear:
            deleted = c.execute(
                text("DELETE FROM products WHERE id LIKE :p"), {"p": f"{args.prefix}-%"}
            ).rowcount
            print(f"cleared {deleted} existing {args.prefix}-* rows")
        existing = c.execute(
            text("SELECT count(*) FROM products WHERE id LIKE :p"),
            {"p": f"{args.prefix}-{size_tag}-%"},
        ).scalar_one()
        if existing:
            print(f"{existing} rows already seeded for size {size_tag}; skipping")
            return 0

    rows = build_rows(args.rows, size_tag)
    CHUNK = 500
    with engine.begin() as c:
        for start in range(0, len(rows), CHUNK):
            vals = []
            params = {}
            for j, p in enumerate(rows[start:start + CHUNK]):
                vals.append(
                    f"(:i{j}, :t{j}, :tf{j}, :c{j}, 'living_room', :pr{j}, :im{j}, "
                    f"'https://example.com/seller', true, '[\"#888888\"]'::json, "
                    f"CAST(:st{j} AS json), CAST(:mt{j} AS json), CAST(:pt{j} AS json), 180, 90, 75, 0.9, "
                    f"'{{}}'::json, :v{j}, CAST(:e{j} AS vector), now(), now())"
                )
                params.update({
                    f"i{j}": p.id, f"t{j}": p.title, f"tf{j}": p.title_fa,
                    f"c{j}": p.category, f"pr{j}": p.price_toman,
                    f"im{j}": p.image_url,
                    f"st{j}": json.dumps(p.styles),
                    f"mt{j}": json.dumps(p.materials),
                    f"pt{j}": json.dumps(p.patterns),
                    f"v{j}": p.is_verified,
                    f"e{j}": "[" + ",".join(f"{x:.6f}" for x in p.style_embedding) + "]",
                })
            c.execute(text(
                "INSERT INTO products (id, title, title_fa, category, room_type, "
                "price_toman, image_url, seller_link, seller_link_ok, colors, styles, "
                "materials, patterns, width_cm, depth_cm, height_cm, "
                "extraction_confidence, extraction_raw, is_verified, style_embedding, "
                "created_at, updated_at) VALUES " + ",".join(vals) +
                " ON CONFLICT (id) DO NOTHING"
            ), params)
        print(f"inserted {len(rows)} rows (prefix {args.prefix}-{size_tag}-*)")
        total = c.execute(select(func.count()).select_from(Product)).scalar_one()
        c.execute(text("ANALYZE products"))
        print(f"total products: {total} (ANALYZE run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
