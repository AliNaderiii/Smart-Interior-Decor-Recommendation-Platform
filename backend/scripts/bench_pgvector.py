#!/usr/bin/env python
"""pgvector query-plan & latency benchmark at realistic catalog sizes.

Master Prompt 04 work item 8: plans + p95 at >=1k and synthetic 10k rows,
cold/warm passes, no-result cases. This script runs the **production Stage A+B
query** (the same filters and ORDER BY as ``_stage_ab_postgres``) against a
real PostgreSQL+pgvector server and records:

* ``EXPLAIN (ANALYZE, BUFFERS)`` plan — whether the HNSW index is used and
  what the post-filter discards;
* latency percentiles (p50/p95/max) for a cold pass and a warm pass of the
  same 56 fused queries (8 quizzes x 7 categories, like 8 /recommend calls);
* ANN recall vs a forced-exact scan at the configured ``hnsw.ef_search``;
* candidate survival (rows reaching Stage C vs ``candidate_limit``);
* no-result query latency (a budget window that matches nothing).

Requirements: ``DATABASE_URL`` must point at PostgreSQL with the pgvector
extension available (``scripts/dev_postgres.py`` provides one via pgserver).
Apply migrations and load the synthetic catalog first (see the evidence
transcript for the exact command sequence).

Usage:
    DATABASE_URL=postgresql+psycopg://... python scripts/bench_pgvector.py \
        --sizes 1000,10000 --json out.json

Every number is DB-level (no Redis / no HTTP) — end-to-end /recommend latency
adds the app cache and serialization; that split is documented in the
evaluation report. Hash embeddings are used for query construction; they make
the run hermetic and do not change index/planner behaviour, but semantic
quality is NOT measured here (see the extraction benchmark for that).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from ai.embedding_service import get_embedding  # noqa: E402
from ai.model_registry import ai_version_info  # noqa: E402
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
    "minimal style living room furniture, colors #FFFFFF #EDEDED",
    "classic style living room furniture made of wood",
    "modern style living room furniture made of leather",
    "scandinavian style living room furniture, colors #F2E8D5",
]
CATEGORIES = ["sofa", "coffee_table", "rug", "lighting", "chair", "storage", "decor"]


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]


def build_params() -> list[dict]:
    params = []
    for qt in QUIZ_TEXTS:
        emb = "[" + ",".join(f"{x:.6f}" for x in get_embedding(qt)) + "]"
        for cat in CATEGORIES:
            params.append({"emb": emb, "category": cat, "lo": LO, "hi": HI,
                           "limit": CANDIDATE_LIMIT})
    return params


def run_pass(conn, params: list[dict]) -> tuple[list[float], int]:
    latencies: list[float] = []
    rows_returned = 0
    for p in params:
        t0 = time.perf_counter()
        rows = conn.execute(QUERY, p).fetchall()
        latencies.append(time.perf_counter() - t0)
        rows_returned += len(rows)
    return latencies, rows_returned


def bench_size(engine, size: int) -> dict:
    out: dict = {"catalog_size": size}
    with engine.connect() as conn:
        conn.execute(text(f"SET hnsw.ef_search = {int(settings.HNSW_EF_SEARCH)}"))
        out["rows_total"] = conn.execute(text("SELECT count(*) FROM products")).scalar_one()
        out["rows_verified"] = conn.execute(
            text("SELECT count(*) FROM products WHERE is_verified")
        ).scalar_one()

        # --- query plan for one representative fused query ---
        probe = build_params()[0]
        emb_literal = probe["emb"]
        plan_sql = (
            "EXPLAIN (ANALYZE, BUFFERS, COSTS) SELECT id FROM products "
            "WHERE room_type = 'living_room' AND category = 'sofa' "
            "AND is_verified = true AND price_toman BETWEEN "
            f"{LO} AND {HI} AND style_embedding IS NOT NULL "
            f"ORDER BY style_embedding <=> '{emb_literal}'::vector, id "
            f"LIMIT {CANDIDATE_LIMIT}"
        )
        plan_text = "\n".join(
            r[0] for r in conn.execute(text(plan_sql)).fetchall()
        )
        out["plan"] = plan_text
        out["plan_uses_hnsw"] = "hnsw" in plan_text.lower()
        out["plan_uses_seq_scan"] = "Seq Scan" in plan_text

        # --- latency: cold pass (first execution after load), then warm ---
        params = build_params()
        cold_lat, cold_rows = run_pass(conn, params)
        warm_lat, warm_rows = run_pass(conn, params)
        for name, lat, rows in (("cold", cold_lat, cold_rows), ("warm", warm_lat, warm_rows)):
            out[f"{name}_p50_ms"] = round(pct(lat, 0.50) * 1000, 1)
            out[f"{name}_p95_ms"] = round(pct(lat, 0.95) * 1000, 1)
            out[f"{name}_max_ms"] = round(max(lat) * 1000, 1)
            out[f"{name}_mean_rows_per_query"] = round(rows / len(lat), 1)

        # --- recall vs forced-exact scan (indexes disabled for one query) ---
        conn.execute(text("SET enable_indexscan = off"))
        conn.execute(text("SET enable_bitmapscan = off"))
        try:
            exact = [r[0] for r in conn.execute(QUERY, {
                "emb": probe["emb"], "category": "sofa", "lo": LO, "hi": HI,
                "limit": CANDIDATE_LIMIT,
            }).fetchall()]
        finally:
            conn.execute(text("SET enable_indexscan = on"))
            conn.execute(text("SET enable_bitmapscan = on"))
        ann = [r[0] for r in conn.execute(QUERY, {
            "emb": probe["emb"], "category": "sofa", "lo": LO, "hi": HI,
            "limit": CANDIDATE_LIMIT,
        }).fetchall()]
        out["exact_candidates_sofa"] = len(exact)
        out["ann_candidates_sofa"] = len(ann)
        out["recall_at_limit_sofa"] = (
            round(len(set(exact) & set(ann)) / len(set(exact)), 4) if exact else None
        )

        # --- no-result query (impossible budget window) ---
        t0 = time.perf_counter()
        conn.execute(QUERY, {
            "emb": probe["emb"], "category": "sofa", "lo": 1, "hi": 10,
            "limit": CANDIDATE_LIMIT,
        }).fetchall()
        out["no_result_ms"] = round((time.perf_counter() - t0) * 1000, 1)

        # --- HNSW index probe: ef_search 40 (pgvector default) vs configured ---
        # The planner legitimately prefers an exact bitmap+sort for the
        # *filtered* production query at these catalog sizes (cheaper and
        # recall 1.0 — recorded above). To exercise the ANN index and the
        # ef_search knob themselves, this section runs the *unfiltered*
        # semantic ORDER BY, where the planner reliably chooses the HNSW
        # index scan. The rows-returned number is the finding: at the pgvector
        # default ef_search=40 the index can return far fewer rows than the
        # LIMIT asks for — the same truncation measured in V2 Phase 2.
        ann = {}
        for ef in (40, settings.HNSW_EF_SEARCH):
            conn.execute(text(f"SET hnsw.ef_search = {int(ef)}"))
            t0 = time.perf_counter()
            rows = conn.execute(text(
                "SELECT id FROM products WHERE style_embedding IS NOT NULL "
                f"ORDER BY style_embedding <=> '{probe['emb']}'::vector "
                f"LIMIT {CANDIDATE_LIMIT}"
            )).fetchall()
            dt = (time.perf_counter() - t0) * 1000
            ann[f"ef{ef}"] = {"rows_returned": len(rows), "latency_ms": round(dt, 1)}
        plan_ann = "\n".join(
            r[0] for r in conn.execute(text(
                "EXPLAIN (ANALYZE) SELECT id FROM products WHERE style_embedding IS NOT NULL "
                f"ORDER BY style_embedding <=> '{probe['emb']}'::vector LIMIT {CANDIDATE_LIMIT}"
            )).fetchall()
        )
        conn.execute(text(f"SET hnsw.ef_search = {int(settings.HNSW_EF_SEARCH)}"))
        out["hnsw_probe"] = ann
        out["hnsw_probe_plan_uses_index"] = "ix_products_style_embedding" in plan_ann
        out["hnsw_probe_plan"] = plan_ann
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="1000,10000")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    if not settings.is_postgres:
        print("ERROR: DATABASE_URL must be PostgreSQL for this benchmark "
              f"(got {settings.DATABASE_URL!r})")
        return 2

    engine = create_engine(settings.DATABASE_URL)
    results: list[dict] = []
    for size in [int(s) for s in args.sizes.split(",")]:
        print(f"\n===== catalog size {size} =====", flush=True)
        r = bench_size(engine, size)
        results.append(r)
        for k, v in r.items():
            if k == "plan":
                print("plan:\n  " + v.replace("\n", "\n  "))
            else:
                print(f"{k}: {v}")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "versions": ai_version_info(),
            "environment": {
                "hnsw_ef_search": settings.HNSW_EF_SEARCH,
                "candidate_limit": CANDIDATE_LIMIT,
                "budget_window_toman": [LO, HI],
                "note": "DB-level latency; pgserver PostgreSQL 16.2 + pgvector 0.6.2 "
                        "sandbox unless stated otherwise",
            },
            "results": results,
        }, indent=2) + "\n")
        print(f"\njson written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
