"""Seed 100 SYNTHETIC demo living-room products (development / CI only).

ADR-016 (catalog integrity): every row this script writes is stamped
``source="synthetic-demo"`` and fails the production tier of the integrity
gate (``synthetic_row``) — it is a demo catalog, never inventory. In
``APP_ENV=production`` the script refuses to run unless ``--allow-synthetic``
is passed explicitly. Rows are now category-consistent (a rug gets a rug photo,
textile materials, a rug-shaped dimension band and a Persian title), which is
what the truth tier of the gate checks and what the 2026-09-07 live probe
found broken (a "rug" whose picture was a sofa, made of metal and leather).

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
  * Production: real CLIP vectors — generate once on an egress-enabled machine
    with `--real-embeddings`, then ship `seed_data/embeddings_real.json` to the
    deployment as a controlled artifact or mounted volume (never commit it to
    git) and seed offline with `--from-json`.

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

# Real Unsplash photo ids, curated PER CATEGORY (visually checked 2026-09-07;
# every id answered HTTP 200 on images.unsplash.com). The pre-ADR-016 seed used
# one shared list indexed by row number, so a rug could carry a sofa photo.
PHOTO_IDS_BY_CATEGORY: dict[str, list[str]] = {
    "sofa": [
        "1555041469-a586c61ea9bc", "1493663284031-b7e3aefcae8e", "1550254478-ead40cc54513",
        "1567016432779-094069958ea5", "1540574163026-643ea20ade25", "1583847268964-b28dc8f51f92",
        "1611967164521-abae8fba4668", "1631679706909-1844bbd07221", "1615873968403-89e068629265",
        "1534889156217-d643df14f14a", "1519710164239-da123dc03ef4", "1538688525198-9b88f6f53126",
        "1524758631624-e2822e304c36",
    ],
    "coffee_table": [
        "1581428982868-e410dd047a90", "1647967527216-adea2f078e07", "1692262089751-7e26b69ad8d1",
        "1594125674956-61a9b49c8ecc", "1600623050499-84929aad17c9", "1599327285939-4ee9088f2b65",
        "1586023492125-27b2c045efd7", "1505693416388-ac5ce068fe85",
    ],
    "rug": [
        "1652634213812-f0deeb1de78e", "1660394585016-508f949df960", "1572123979839-3749e9973aba",
        "1531162805941-58330188d75c", "1600166898405-da9535204843", "1765802536365-e2267a489a2c",
        "1762356317094-5826049a3641", "1745905308908-25f35bacd146", "1766405831946-2b7f1653ed8f",
        "1762758889413-64d717f81b0d",
    ],
    "lighting": [
        "1507473885765-e6ed057f782c", "1540932239986-30128078f3c5", "1513506003901-1e6a229e2d15",
        "1494438639946-1ebd1d20bf85", "1517991104123-1d56a6e81ed9", "1621177555630-b861919c864f",
        "1580130281320-0ef0754f2bf7", "1571508601891-ca5e7a713859",
    ],
    "chair": [
        "1580480055273-228ff5388ef8", "1567538096630-e0c55bd6374c", "1601366533287-5ee4c763ae4e",
        "1598300042247-d088f8ab3a91", "1634712282287-14ed57b9cc89", "1616486338812-3dadae4b4ace",
    ],
    "storage": [
        "1594026112284-02bb6f3352fe", "1713810958247-01dbd76b4a61", "1721385675060-9982ec72385e",
        "1618220048045-10a6dbdf83e0", "1612908317776-a3afde8232fa", "1628152371231-936cf45eb8f3",
        "1593430980369-68efc5a5eb34", "1605116959031-6e2d13a2ee56", "1536411396596-afed9fa3c1b2",
        "1618220179428-22790b461013",
    ],
    "decor": [
        "1584100936595-c0654b55a2e2", "1629949009765-40fc74c9ec21", "1553114552-c4ece3a33c93",
        "1531877025030-f7696a50770f", "1572427734891-5592aae758b2", "1691256676366-370303d55b61",
        "1580229080435-1c7e2ce835c1",
    ],
}

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

# Keyed by the seven taxonomy categories directly (the old armchair/tv_stand/
# bookshelf/curtain keys were aliased into chair/storage/decor and the 8-way
# split produced 12–13 rows per taxonomy category anyway). ``materials`` is the
# per-category plausible subset the integrity gate enforces; ``fa`` is a real
# Persian product noun used to build ``title_fa``.
CATEGORY_DEFS = {
    "sofa": {"price": (18_000_000, 120_000_000), "size": ((180, 260), (85, 105), (70, 95)),
             "fa": "مبل راحتی", "materials": ["fabric", "leather", "wood", "metal"]},
    "coffee_table": {"price": (3_000_000, 30_000_000), "size": ((80, 140), (50, 80), (35, 50)),
                     "fa": "میز جلومبلی", "materials": ["wood", "metal", "glass", "rattan"]},
    "rug": {"price": (5_000_000, 80_000_000), "size": ((200, 350), (140, 250), (1, 2)),
            "fa": "فرش", "materials": ["fabric"]},
    "lighting": {"price": (1_500_000, 25_000_000), "size": ((25, 60), (25, 60), (40, 180)),
                 "fa": "چراغ ایستاده", "materials": ["metal", "glass", "wood", "fabric", "rattan"]},
    "chair": {"price": (8_000_000, 45_000_000), "size": ((70, 95), (75, 95), (75, 100)),
              "fa": "صندلی راحتی", "materials": ["wood", "fabric", "leather", "metal", "rattan"]},
    "storage": {"price": (5_000_000, 40_000_000), "size": ((60, 220), (25, 50), (45, 220)),
                "fa": "بوفه و کتابخانه", "materials": ["wood", "metal", "glass", "rattan"]},
    # decor photos are cushions/textiles, so the material pool is textile-only
    # and title ↔ picture agree (the gate itself allows more for real rows).
    "decor": {"price": (2_000_000, 18_000_000), "size": ((40, 140), (1, 40), (40, 280)),
              "fa": "کوسن و پرده", "materials": ["fabric"]},
}

STYLE_FA = {
    "modern": "مدرن", "scandinavian": "اسکاندیناوی", "industrial": "صنعتی",
    "boho": "بوهو", "minimal": "مینیمال", "classic": "کلاسیک",
}
MATERIAL_FA = {
    "wood": "چوب گردو", "metal": "فلز مشکی", "fabric": "پارچه کتان",
    "leather": "چرم عسلی", "glass": "شیشه سکوریت", "rattan": "حصیر طبیعی",
}
# How the primary material reads in a title for that category (a rug is
# «پشمی», not «پارچه کتان»; a sofa has «فریم چوبی», it is not «چوب گردو»).
MATERIAL_FA_BY_CATEGORY: dict[str, dict[str, str]] = {
    "sofa": {"wood": "با فریم چوبی", "metal": "با پایه فلزی", "fabric": "پارچه‌ای", "leather": "چرمی"},
    "chair": {"wood": "چوبی", "metal": "با پایه فلزی", "fabric": "پارچه‌ای", "leather": "چرمی", "rattan": "حصیری"},
    "coffee_table": {"wood": "چوبی", "metal": "فلزی", "glass": "با صفحهٔ شیشه‌ای", "rattan": "حصیری"},
    "storage": {"wood": "چوبی", "metal": "فلزی", "glass": "با درب شیشه‌ای", "rattan": "حصیری"},
    "rug": {"fabric": "پشمی"},
    "lighting": {"fabric": "با آباژور پارچه‌ای", "glass": "با حباب شیشه‌ای", "metal": "فلزی",
                 "wood": "با پایه چوبی", "rattan": "حصیری"},
    "decor": {"fabric": "مخمل"},
}


def material_fa(category: str, material: str) -> str:
    return MATERIAL_FA_BY_CATEGORY.get(category, {}).get(material, MATERIAL_FA[material])

MATERIAL_WORDS = {
    "wood": "walnut wood", "metal": "black metal", "fabric": "linen fabric",
    "leather": "cognac leather", "glass": "tempered glass", "rattan": "natural rattan",
}

# Demo rows have no real listing behind them, so the links stay category
# landing pages ON PURPOSE — the integrity gate reports them as
# ``seller_link_shallow`` (production-blocking), which is the truthful state.
SELLER_LINKS = [
    "https://www.digikala.com/main/home-and-kitchen/",
    "https://torob.com/browse/1029/مبلمان/",
    "https://www.digikala.com/search/category-home-decoration/",
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
    """Generate 100 deterministic, category-consistent SYNTHETIC products."""
    precomputed = _load_real_embeddings() if real_from_json else None
    if real_from_json and precomputed is None:
        print("WARNING: seed_data/embeddings_real.json not found — "
              "falling back to the configured EMBEDDING_BACKEND. "
              "Generate it with: python scripts/seed_products.py --real-embeddings")
    products: list[Product] = []
    styles = list(STYLE_DEFS.keys())
    categories = list(CATEGORY_DEFS.keys())
    per_category_serial: dict[str, int] = {c: 0 for c in categories}
    i = 0
    while len(products) < 100:
        style = styles[i % len(styles)]
        category = categories[(i // len(styles)) % len(categories)]
        sdef, cdef = STYLE_DEFS[style], CATEGORY_DEFS[category]
        # Materials: the style's palette of materials intersected with what is
        # physically plausible for the category (a rug is never metal).
        pool = [m for m in sdef["materials"] if m in cdef["materials"]] or list(cdef["materials"])
        materials = random.sample(pool, k=min(2, len(pool)))
        colors = random.sample(sdef["colors"], k=2)
        adjective = random.choice(sdef["adjectives"])
        material_word = MATERIAL_WORDS[materials[0]]
        pattern = "persian" if (category == "rug" and style == "classic") else (
            random.choice(PATTERNS[:3]) if category in ("rug", "decor") else "solid"
        )
        lo, hi = cdef["price"]
        price = int(round(random.uniform(lo, hi), -5))
        (w0, w1), (d0, d1), (h0, h1) = cdef["size"]
        serial = per_category_serial[category] = per_category_serial[category] + 1
        title = f"{adjective.title()} {style.title()} {category.replace('_', ' ').title()} — {material_word.title()}"
        title_fa = f"{cdef['fa']} {STYLE_FA[style]} {material_fa(category, materials[0])} مدل {serial}"
        description = (
            f"a {style} {category.replace('_', ' ')} in {adjective} design, "
            f"made of {' and '.join(materials)}, {material_word} finish, {pattern} pattern"
        )
        photos = PHOTO_IDS_BY_CATEGORY[category]
        product = Product(
            title=title,
            title_fa=title_fa,
            category=category,
            room_type="living_room",
            price_toman=price,
            image_url=UNSPLASH.format(pid=photos[(serial - 1) % len(photos)]),
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
            extraction_raw={"source": "synthetic-demo", "detected_category": category},
            is_verified=True,
            source="synthetic-demo",
            source_product_id=f"demo-{category}-{serial:03d}",
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


def seed(
    if_empty: bool = False,
    real_embeddings: bool = False,
    from_json: bool = False,
    allow_synthetic: bool = False,
) -> None:
    """Create tables (dev), seed products and default accounts.

    ADR-016: refuses to write synthetic rows into a production database unless
    ``allow_synthetic`` is set (CLI ``--allow-synthetic``). Even then the rows
    are stamped ``source="synthetic-demo"`` and the production integrity gate
    excludes them from recommendations — the flag only lets an operator
    populate a staging/preview deployment, it cannot make demo data sellable.
    """
    from app.core.config import settings as _settings

    # Production fail-safe (ADR-016). Exit 0, like the demo-account refusal:
    # the compose/Render start commands run this script on every boot and a
    # hard failure there would take the API down instead of keeping demo data
    # out. The message is the operator's signal; the empty catalog is visible
    # in /admin/stats and /health.
    refuse_synthetic = _settings.is_production and not allow_synthetic
    if refuse_synthetic:
        print(
            "REFUSING to seed synthetic demo products: APP_ENV=production and "
            "seed_products.py only writes source=synthetic-demo rows, which a sold "
            "deployment must never recommend. Import a real catalog instead "
            "(scripts/load_realistic_products.py is a curated SAMPLE, not inventory; "
            "see docs/ARCHITECTURE.md ADR-016) or pass --allow-synthetic for a "
            "preview deployment — the integrity gate still excludes those rows.",
            file=sys.stderr,
        )
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
        if refuse_synthetic:
            print(f"products table left untouched ({count} rows)")
        elif if_empty and count > 0:
            print(f"products table already has {count} rows; skipping seed")
        else:
            products = build_products(real_from_json=from_json)
            for product in products:
                db.add(product)
            db.flush()
            # Stamp the integrity verdict at write time, exactly as the admin
            # routes do, so the recommender and /admin/stats see the same truth.
            from app.services import catalog_integrity as integrity

            index = integrity.image_index(db, products)
            for product in products:
                integrity.refresh(product, db, known_images=index, keep_override=False)
            db.commit()
            excluded = sum(1 for p in products if p.integrity_ok is False)
            print(
                f"seeded {len(products)} SYNTHETIC demo products "
                f"(source=synthetic-demo; integrity strict={integrity.strict_mode()}, "
                f"excluded={excluded})"
            )
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
            allow_synthetic="--allow-synthetic" in sys.argv,
        )
