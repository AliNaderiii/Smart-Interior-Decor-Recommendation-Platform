"""Seed 100 realistic living-room products with precomputed embeddings.

Usage:
    python scripts/seed_products.py                    # seed (skip if present)
    python scripts/seed_products.py --if-empty         # only when table empty
    python scripts/seed_products.py --real-embeddings  # force CLIP ViT-B/32 and
                                                       # export seed_data/embeddings_real.json
    python scripts/seed_products.py --from-json        # load precomputed real
                                                       # embeddings from that JSON
                                                       # (no model download needed)

Embedding strategy (see docs/ARCHITECTURE.md ADR-004):
  * CI / offline dev: deterministic hash embeddings (EMBEDDING_BACKEND=hash)
  * Production: real CLIP vectors — generate once on a networked machine with
    `--real-embeddings`, commit `seed_data/embeddings_real.json`, then any
    offline deploy can seed with `--from-json`.

Demo accounts (Stage 03 / IR-001):
    This script no longer creates default logins unconditionally. Demo accounts
    are created only when ``SEED_DEMO_ACCOUNTS=true`` **and** ``APP_ENV`` is not
    ``production``; the gate and the credential list live in
    ``app.core.demo_seed``. See docs/security/DEMO_ACCOUNTS.md.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from ai.embedding_service import get_embedding, product_to_text  # noqa: E402
from app.core.demo_seed import ensure_demo_accounts  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import Base, Product  # noqa: E402

random.seed(42)

UNSPLASH = "https://images.unsplash.com/photo-{pid}?w=800&q=70&fm=webp"

# Real Unsplash living-room / furniture photo ids (stable CDN URLs)
PHOTO_IDS = [
    "1555041469-a586c61ea9bc", "1493663284031-b7e3aefcae8e", "1550254478-ead40cc54513",
    "1567016432779-094069958ea5", "1583847268964-b28dc8f51f92", "1586023492125-27b2c045efd7",
    "1598300042247-d088f8ab3a91", "1616486338812-3dadae4b4ace", "1618220179428-22790b461013",
    "1615873968403-89e068629265", "1616627981431-2c3c4bd0f99e", "1616594039964-ae9021a400a0",
    "1631679706909-1844bbd07221", "1615529182904-14819c35db37", "1540574163026-643ea20ade25",
    "1519710164239-da123dc03ef4", "1538688525198-9b88f6f53126", "1524758631624-e2822e304c36",
    "1505693416388-ac5ce068fe85", "1571508601891-ca5e7a713859",
]

STYLE_DEFS = {
    "modern": {
        "colors": ["#2E2E2E", "#FFFFFF", "#8A8A8A", "#3B5B7A"],
        "materials": ["metal", "glass", "leather"],
        "adjectives": ["sleek", "contemporary", "clean-lined"],
    },
    "scandinavian": {
        "colors": ["#F2E8D5", "#D9CBB3", "#C8A165", "#FFFFFF"],
        "materials": ["wood", "fabric"],
        "adjectives": ["light oak", "airy", "hygge"],
    },
    "industrial": {
        "colors": ["#1A1A1A", "#6D4C33", "#5B5B5B", "#8B4513"],
        "materials": ["metal", "wood", "leather"],
        "adjectives": ["raw steel", "loft", "reclaimed"],
    },
    "boho": {
        "colors": ["#C1633F", "#D9A05B", "#4C6444", "#E8D5B7"],
        "materials": ["rattan", "fabric", "wood"],
        "adjectives": ["woven", "eclectic", "earthy"],
    },
    "minimal": {
        "colors": ["#FFFFFF", "#EDEDED", "#CFCFCF", "#1A1A1A"],
        "materials": ["wood", "metal"],
        "adjectives": ["pared-back", "essential", "quiet"],
    },
    "classic": {
        "colors": ["#6D4C33", "#7B1E26", "#D4AF37", "#3E2C1C"],
        "materials": ["wood", "fabric", "leather"],
        "adjectives": ["ornate", "timeless", "elegant"],
    },
}

CATEGORY_DEFS = {
    "sofa": {"price": (18_000_000, 120_000_000), "size": ((180, 260), (85, 105), (70, 95)), "fa": "مبل"},
    "coffee_table": {"price": (3_000_000, 30_000_000), "size": ((80, 140), (50, 80), (35, 50)), "fa": "میز جلومبلی"},
    "rug": {"price": (5_000_000, 80_000_000), "size": ((200, 350), (140, 250), (1, 2)), "fa": "فرش"},
    "lighting": {"price": (1_500_000, 25_000_000), "size": ((25, 60), (25, 60), (40, 180)), "fa": "چراغ"},
    "armchair": {"price": (8_000_000, 45_000_000), "size": ((70, 95), (75, 95), (75, 100)), "fa": "صندلی راحتی"},
    "tv_stand": {"price": (6_000_000, 40_000_000), "size": ((140, 220), (35, 50), (45, 65)), "fa": "میز تلویزیون"},
    "bookshelf": {"price": (5_000_000, 35_000_000), "size": ((60, 120), (25, 40), (150, 220)), "fa": "کتابخانه"},
    "curtain": {"price": (2_000_000, 18_000_000), "size": ((140, 300), (1, 2), (240, 280)), "fa": "پرده"},
}

CATEGORY_ALIASES = {
    "armchair": "chair",
    "tv_stand": "storage",
    "bookshelf": "storage",
    "curtain": "decor",
}

MATERIAL_WORDS = {
    "wood": "walnut wood", "metal": "black metal", "fabric": "linen fabric",
    "leather": "cognac leather", "glass": "tempered glass", "rattan": "natural rattan",
}

SELLER_LINKS = [
    "https://www.digikala.com/",
    "https://torob.com/",
    "https://www.digikala.com/main/home-and-kitchen/",
]

PATTERNS = ["solid", "geometric", "floral", "striped", "abstract", "persian"]


EMBEDDINGS_JSON = Path(__file__).resolve().parents[1] / "seed_data" / "embeddings_real.json"


def _load_real_embeddings() -> dict[str, list[float]] | None:
    """Load committed real-CLIP embeddings keyed by product title, if present."""
    if EMBEDDINGS_JSON.exists():
        import json

        return json.loads(EMBEDDINGS_JSON.read_text())
    return None


def _export_real_embeddings(products: list[Product]) -> None:
    """Write {title: embedding} JSON so offline deploys can reuse real vectors."""
    import json

    EMBEDDINGS_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {p.title: list(p.style_embedding) for p in products}
    EMBEDDINGS_JSON.write_text(json.dumps(payload))
    print(f"exported {len(payload)} real embeddings -> {EMBEDDINGS_JSON}")


def build_products(real_from_json: bool = False) -> list[Product]:
    """Generate 100 deterministic, realistic products across 8 categories."""
    precomputed = _load_real_embeddings() if real_from_json else None
    if real_from_json and precomputed is None:
        print("WARNING: seed_data/embeddings_real.json not found — "
              "falling back to the configured EMBEDDING_BACKEND. "
              "Generate it with: python scripts/seed_products.py --real-embeddings")
    products: list[Product] = []
    styles = list(STYLE_DEFS.keys())
    categories = list(CATEGORY_DEFS.keys())
    i = 0
    while len(products) < 100:
        style = styles[i % len(styles)]
        category = categories[(i // len(styles)) % len(categories)]
        sdef, cdef = STYLE_DEFS[style], CATEGORY_DEFS[category]
        materials = random.sample(sdef["materials"], k=min(2, len(sdef["materials"])))
        colors = random.sample(sdef["colors"], k=2)
        adjective = random.choice(sdef["adjectives"])
        material_word = MATERIAL_WORDS[materials[0]]
        pattern = "persian" if (category == "rug" and style == "classic") else (
            random.choice(PATTERNS[:3]) if category in ("rug", "curtain") else "solid"
        )
        lo, hi = cdef["price"]
        price = int(round(random.uniform(lo, hi), -5))
        (w0, w1), (d0, d1), (h0, h1) = cdef["size"]
        title = f"{adjective.title()} {style.title()} {category.replace('_', ' ').title()} — {material_word.title()}"
        description = (
            f"a {style} {category.replace('_', ' ')} in {adjective} design, "
            f"made of {' and '.join(materials)}, {material_word} finish, {pattern} pattern"
        )
        product = Product(
            title=title,
            title_fa=f"{CATEGORY_DEFS[category]['fa']} {style}",
            category=CATEGORY_ALIASES.get(category, category),
            room_type="living_room",
            price_toman=price,
            image_url=UNSPLASH.format(pid=PHOTO_IDS[i % len(PHOTO_IDS)]),
            seller_link=SELLER_LINKS[i % len(SELLER_LINKS)],
            seller_link_ok=True,
            colors=colors,
            styles=[style],
            materials=materials,
            patterns=[pattern],
            width_cm=random.randint(w0, w1),
            depth_cm=random.randint(d0, d1),
            height_cm=random.randint(h0, h1),
            description=description,
            extraction_confidence=round(random.uniform(0.82, 0.97), 2),
            is_verified=True,
        )
        if precomputed and title in precomputed:
            product.style_embedding = precomputed[title]
        else:
            product.style_embedding = get_embedding(
                product_to_text(title, [style], colors, materials, description, [pattern])
            )
        products.append(product)
        i += 1
    return products


def seed(if_empty: bool = False, real_embeddings: bool = False, from_json: bool = False) -> None:
    """Create tables (dev), seed products and default accounts."""
    if real_embeddings:
        # Force the CLIP backend regardless of env; fails loudly if the model
        # can't be loaded so we never silently commit hash vectors as "real".
        import ai.embedding_service as es

        es._backend = None  # reset resolution cache
        from app.core.config import settings as _s

        object.__setattr__(_s, "EMBEDDING_BACKEND", "clip")
        if es._load_clip() is None:
            raise SystemExit(
                "ERROR: --real-embeddings requires the CLIP model "
                "(pip install sentence-transformers torch + internet on first run)."
            )

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        count = db.scalar(select(func.count(Product.id))) or 0
        if if_empty and count > 0:
            print(f"products table already has {count} rows; skipping seed")
        else:
            products = build_products(real_from_json=from_json)
            for product in products:
                db.add(product)
            db.commit()
            print("seeded 100 products")
            if real_embeddings:
                _export_real_embeddings(products)

        defaults_created = ensure_demo_accounts(db)
        db.commit()
        if defaults_created:
            print(
                "DEVELOPMENT ONLY: demo accounts created "
                f"({', '.join(defaults_created)}) — see docs/security/DEMO_ACCOUNTS.md"
            )
        else:
            print(
                "demo accounts not created (production, or SEED_DEMO_ACCOUNTS "
                "is false — this is the safe default)"
            )
    finally:
        db.close()


if __name__ == "__main__":
    if "--seed-demo-accounts" in sys.argv:
        # DEV ONLY. enable_for_this_process() raises under APP_ENV=production,
        # so a deploy script cannot quietly get demo logins.
        from app.core.demo_seed import enable_for_this_process

        enable_for_this_process(reason="--seed-demo-accounts")
    if "--realistic" in sys.argv:
        # Backward-compatible entrypoint for deploy scripts that still call
        # seed_products.py. The dedicated loader owns realistic data mapping.
        from scripts.load_realistic_products import load

        expand_to = 150
        if "--expand-to" in sys.argv:
            expand_to = int(sys.argv[sys.argv.index("--expand-to") + 1])
        load(
            if_empty="--if-empty" in sys.argv,
            clear="--clear" in sys.argv,
            expand_to=expand_to,
            from_json="--from-json" in sys.argv,
        )
    else:
        seed(
            if_empty="--if-empty" in sys.argv,
            real_embeddings="--real-embeddings" in sys.argv,
            from_json="--from-json" in sys.argv,
        )
