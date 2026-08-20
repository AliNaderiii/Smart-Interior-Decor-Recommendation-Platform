"""Load curated Persian products with real dimensions and retailer links.

Usage:
    python scripts/load_realistic_products.py --realistic --if-empty
    python scripts/load_realistic_products.py --realistic --expand-to 150 --clear
    python scripts/load_realistic_products.py --realistic --from-json

The committed 150-row catalog is deterministic demo data expanded from 20
curated samples. Hash embeddings keep offline development functional; CLIP can
be selected with EMBEDDING_BACKEND=clip. Precomputed vectors are used when
``--from-json`` is supplied and ``seed_data/embeddings_real.json`` exists.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402

from ai.embedding_service import get_backend, get_embedding, product_to_text  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import Base, Product, Subscription, User  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("realistic-products")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
SAMPLE_PATHS = [REPO_ROOT / "datasets/products_realistic.json", BACKEND_ROOT / "seed_data/products_realistic.json"]
EXPANDED_PATHS = [REPO_ROOT / "datasets/products_realistic_150.json", BACKEND_ROOT / "seed_data/products_realistic_150.json"]
EMBEDDINGS_JSON = BACKEND_ROOT / "seed_data/embeddings_real.json"
RETAILER_HOSTS = {"www.digikala.com", "digikala.com", "torob.com", "www.torob.com", "khoonehroya.ir", "www.khoonehroya.ir"}


def _first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError("Realistic dataset not found. Checked: " + ", ".join(map(str, paths)))


def read_products(expand_to: int | None = None) -> list[dict]:
    paths = EXPANDED_PATHS if expand_to and expand_to > 20 else SAMPLE_PATHS
    path = _first_existing(paths)
    rows = json.loads(path.read_text(encoding="utf-8"))
    if expand_to:
        if expand_to > len(rows):
            logger.warning("Requested %d rows but committed catalog has %d; loading all", expand_to, len(rows))
        rows = rows[:expand_to]
    logger.info("Reading %d realistic products from %s", len(rows), path)
    return rows


def _precomputed(enabled: bool) -> dict[str, list[float]]:
    if not enabled:
        return {}
    if not EMBEDDINGS_JSON.exists():
        logger.warning(
            "seed_data/embeddings_real.json is absent; using configured embedding backend. "
            "Generate it on a networked machine with seed_products.py --real-embeddings"
        )
        return {}
    return json.loads(EMBEDDINGS_JSON.read_text(encoding="utf-8"))


def to_model(row: dict, embeddings: dict[str, list[float]]) -> Product:
    dimensions = row["dimensions_cm"]
    title_fa = row["title_fa"]
    styles = row.get("style_tags", [])
    colors = row.get("color_palette", [])
    materials = row.get("material_tags", [])
    description = row.get("description_for_embedding", "")
    embedding = embeddings.get(row.get("id")) or embeddings.get(title_fa)
    if embedding is None:
        embedding = get_embedding(product_to_text(title_fa, styles, colors, materials, description))
    host = (urlparse(row.get("seller_link", "")).hostname or "").lower()
    return Product(
        title=title_fa,
        title_fa=title_fa,
        category=row["category"],
        room_type=row.get("room_type", "living_room"),
        price_toman=int(row["price_toman"]),
        image_url=row["image_url"],
        seller_link=row.get("seller_link", ""),
        seller_link_ok=host in RETAILER_HOSTS,
        colors=colors,
        styles=styles,
        materials=materials,
        patterns=row.get("pattern_tags", ["solid"]),
        width_cm=int(dimensions["length"]),
        depth_cm=int(dimensions["width"]),
        height_cm=int(dimensions["height"]),
        description=description,
        extraction_confidence=1.0,
        extraction_raw={"dataset_id": row.get("id"), "seller": row.get("seller"), "source": "realistic_dataset_v3"},
        is_verified=True,
        style_embedding=embedding,
    )


def ensure_default_accounts(db) -> None:
    defaults = [
        ("admin@smartdecor.dev", "Admin123!", "admin", "Platform Admin"),
        ("designer@smartdecor.dev", "Design123!", "designer", "Sara Designer"),
        ("demo@smartdecor.dev", "Demo1234!", "homeowner", "Demo Homeowner"),
    ]
    for email, password, role, name in defaults:
        if not db.scalar(select(User).where(User.email == email)):
            user = User(email=email, hashed_password=hash_password(password), role=role, full_name=name)
            user.subscription = Subscription(plan="free", is_active=False)
            db.add(user)


def load(*, if_empty: bool = False, clear: bool = False, expand_to: int | None = None, from_json: bool = False) -> int:
    Base.metadata.create_all(engine)
    rows = read_products(expand_to)
    embeddings = _precomputed(from_json)
    with SessionLocal() as db:
        count = db.scalar(select(func.count(Product.id))) or 0
        if if_empty and count:
            logger.info("Products table already has %d rows; skipping realistic seed", count)
            ensure_default_accounts(db)
            db.commit()
            return count
        if clear:
            db.execute(delete(Product))
            db.flush()
        products = [to_model(row, embeddings) for row in rows]
        db.add_all(products)
        ensure_default_accounts(db)
        db.commit()
        count = db.scalar(select(func.count(Product.id))) or 0
        average = db.scalar(select(func.avg(Product.price_toman))) or 0
    categories = Counter(row["category"] for row in rows)
    retailer_count = sum(bool(row.get("seller_link")) for row in rows)
    logger.info(
        "Loaded %d realistic products with %d retailer links, avg price %.1fM Toman, categories: %s, embedding=%s; table count=%d",
        len(rows), retailer_count, float(average) / 1_000_000, dict(categories), get_backend(), count,
    )
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--realistic", action="store_true", help="Explicitly select the realistic dataset")
    parser.add_argument("--if-empty", action="store_true")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--from-json", action="store_true")
    parser.add_argument("--expand", action="store_true", help="Alias for --expand-to 150")
    parser.add_argument("--expand-to", type=int)
    args = parser.parse_args()
    expand_to = args.expand_to or (150 if args.expand else None)
    load(if_empty=args.if_empty, clear=args.clear, expand_to=expand_to, from_json=args.from_json)


if __name__ == "__main__":
    main()
