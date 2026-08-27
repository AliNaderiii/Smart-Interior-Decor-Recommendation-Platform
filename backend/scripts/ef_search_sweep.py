#!/usr/bin/env python
"""T-2.2 helper: standalone EXPLAIN ANALYZE + hnsw.ef_search sensitivity.

Runs the production fused Stage A+B query (same SQL as
recommender._stage_ab_postgres, same SET LOCAL hnsw.ef_search discipline)
against the seeded Postgres and emits:
  1. EXPLAIN (ANALYZE, BUFFERS) at the configured ef_search (400);
  2. an ef_search sweep {100, 200, 400, 800}: latency (n=30 each, p50/p95)
     + recall@candidate_limit vs a forced-exact scan.

Usage:
    DATABASE_URL=... python scripts/ef_search_sweep.py [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from ai.embedding_service import get_embedding  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services.recommender import CANDIDATE_LIMIT  # noqa: E402

LO, HI = 1_000_000, 150_000_000

QUERY = text("""
SELECT id FROM products
WHERE room_type = 'living_room' AND category = :category AND is_verified = true
  AND price_toman BETWEEN :lo AND :hi AND style_embedding IS NOT NULL
ORDER BY style_embedding <=> CAST(:emb AS vector), id
LIMIT :limit
""")

QUIZ_TEXTS = [
    "modern style living room furniture, colors #2E2E2E #FFFFFF",
    "scandinavian style living room furniture made of wood and fabric",
    "industrial style living room furniture made of metal",
    "boho style living room furniture made of rattan",
]
CATEGORIES = ["sofa", "rug", "lighting", "chair"]


def pct(vals, q):
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    eng = create_engine(settings.DATABASE_URL)
    emb = "[" + ",".join(f"{x:.6f}" for x in get_embedding(QUIZ_TEXTS[0])) + "]"
    params = {"category": "sofa", "lo": LO, "hi": HI, "emb": emb,
              "limit": CANDIDATE_LIMIT}

    out: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "commit": subprocess.run(["git", "rev-parse", "HEAD"],
                                 capture_output=True, text=True).stdout.strip(),
        "configured_ef_search": int(settings.HNSW_EF_SEARCH),
        "candidate_limit": CANDIDATE_LIMIT,
    }

    with eng.connect() as c:
        out["row_count"] = c.execute(text("select count(*) from products")).scalar()

    # 1. EXPLAIN ANALYZE at the configured ef_search, exactly as production.
    with eng.connect() as c:
        with c.begin():
            c.execute(text(f"SET LOCAL hnsw.ef_search = {int(settings.HNSW_EF_SEARCH)}"))
            plan = "\n".join(
                r[0] for r in c.execute(
                    text("EXPLAIN (ANALYZE, BUFFERS) " + QUERY.text), params))
    out["explain_analyze_ef400"] = plan
    print("=== EXPLAIN (ANALYZE, BUFFERS), SET LOCAL hnsw.ef_search =",
          int(settings.HNSW_EF_SEARCH), "===")
    print(plan)

    # 2. Exact ground truth (disable index scan for this connection only).
    truth: dict[tuple, list] = {}
    with eng.connect() as c:
        with c.begin():
            c.execute(text("SET LOCAL enable_indexscan = off"))
            c.execute(text("SET LOCAL enable_bitmapscan = off"))
            for qt in QUIZ_TEXTS:
                e = "[" + ",".join(f"{x:.6f}" for x in get_embedding(qt)) + "]"
                for cat in CATEGORIES:
                    p = dict(params, category=cat, emb=e)
                    truth[(qt, cat)] = [
                        r[0] for r in c.execute(QUERY, p)]

    # 3. Sweep.
    sweep = {}
    for ef in (100, 200, 400, 800):
        lats, recalls = [], []
        with eng.connect() as c:
            for qt in QUIZ_TEXTS:
                e = "[" + ",".join(f"{x:.6f}" for x in get_embedding(qt)) + "]"
                for cat in CATEGORIES:
                    p = dict(params, category=cat, emb=e)
                    got = None
                    for _ in range(3):  # 3 reps per (quiz, cat) -> n=48/ef... n=3*16=48
                        with c.begin():
                            c.execute(text(f"SET LOCAL hnsw.ef_search = {ef}"))
                            t0 = time.perf_counter()
                            got = [r[0] for r in c.execute(QUERY, p)]
                            lats.append((time.perf_counter() - t0) * 1000.0)
                    exact = truth[(qt, cat)]
                    if exact:
                        recalls.append(len(set(got) & set(exact)) / len(exact))
        sweep[str(ef)] = {
            "n_lat": len(lats),
            "lat_p50_ms": round(pct(lats, 0.5), 2),
            "lat_p95_ms": round(pct(lats, 0.95), 2),
            "lat_mean_ms": round(statistics.fmean(lats), 2),
            "recall_at_limit_mean": round(statistics.fmean(recalls), 4),
            "recall_at_limit_min": round(min(recalls), 4),
        }
        print(f"ef_search={ef}: {sweep[str(ef)]}")
    out["ef_search_sweep"] = sweep

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=2))
        print("json written:", args.json_out)


if __name__ == "__main__":
    main()
