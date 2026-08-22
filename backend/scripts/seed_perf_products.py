"""Bulk-seed synthetic products to exercise pgvector at realistic scale.

V2 Phase 2. The Phase 0B EXPLAIN ANALYZE ran against 100 rows and produced a
Seq Scan, which proves nothing about the HNSW index — Postgres will always
prefer a sequential scan on a tiny table. This script inserts 20k synthetic
products with random unit-norm 512-dim embeddings so the planner has a reason
to use the index, and so post-filter recall (`hnsw.ef_search`) becomes
observable.

Usage:
    source /tmp/env_v2.sh && python scripts/seed_perf_products.py

All rows are prefixed `perf-` and are safe to delete:
    DELETE FROM products WHERE id LIKE 'perf-%';
"""
import os
import random
import sys

sys.path.insert(0, os.getcwd())
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
eng = create_engine(url)
random.seed(42)

CATS = ["sofa", "coffee_table", "rug", "lamp", "art"]
STYLES = ["modern", "minimal", "scandinavian", "bohemian", "industrial", "traditional"]
DIM = 512

with eng.begin() as c:
    n = c.execute(text("select count(*) from products")).scalar()
    print("products before:", n)

rows = []
target = 20000
for i in range(target):
    v = [random.gauss(0, 1) for _ in range(DIM)]
    norm = sum(x * x for x in v) ** 0.5
    v = [x / norm for x in v]
    rows.append({
        "id": f"perf-{i:06d}",
        "title": f"Perf Product {i}",
        "category": random.choice(CATS),
        "room_type": "living_room",
        "price": random.randint(500_000, 90_000_000),
        "styles": '["%s"]' % random.choice(STYLES),
        "emb": "[" + ",".join(f"{x:.6f}" for x in v) + "]",
    })

ins = text("""
insert into products (id, title, title_fa, description, category, room_type,
                      price_toman, image_url, seller_link, seller_link_ok,
                      colors, styles, materials, patterns,
                      width_cm, depth_cm, height_cm,
                      extraction_confidence, extraction_raw, is_verified,
                      style_embedding, created_at, updated_at)
values (:id, :title, :title, 'perf seed', :category, :room_type,
        :price, 'https://example.com/p.jpg', 'https://example.com', true,
        CAST('["#C1633F"]' AS json), CAST(:styles AS json),
        CAST('["wood"]' AS json), CAST('["solid"]' AS json),
        180, 90, 75, 0.9, CAST('{}' AS json), true,
        CAST(:emb AS vector), now(), now())
on conflict (id) do nothing
""")
B = 1000
with eng.begin() as c:
    for i in range(0, len(rows), B):
        c.execute(ins, rows[i:i + B])
        print("  inserted", i + B, flush=True)

with eng.begin() as c:
    print("products after:", c.execute(text("select count(*) from products")).scalar())
