# `/recommend` p95 at HEAD — Stage 2, T-2.2 (`perf_head.md`)

**Contract gate:** `/recommend` API **p95 < 2 s**.
**Status:** LOCAL ITERATION COMPLETE — PASSING WITH WIDE MARGIN · **contract verdict: PENDING CI MEASUREMENT** (supervisor amendment A1: contract-facing numbers must come from the CI environment; everything below is iteration/diagnosis evidence unless marked otherwise).

Historical reference: `docs/PERF_REPORT_V2.md` measured p95 = 546 ms (warm) / 662 ms (cold) @100-concurrency at `a847ad5` (2026-08-19). This document re-measures at HEAD.

---

## 1. Environments

| | Local iteration (this doc §2–§6) | CI evidence of record (§7, pending) |
|---|---|---|
| Host | sandbox, 2 vCPU Intel Xeon @2.60 GHz, 3.8 GiB RAM, Debian 12 | ubuntu-latest, 4 vCPU / 16 GB |
| Postgres | **real Postgres 16 + pgvector** (embedded `pgserver`, same method as PERF_REPORT_V2) | `pgvector/pgvector:pg16` service container |
| Redis | fakeredis (`REDIS_URL` empty) — warm-path numbers therefore **never contract evidence** | `redis:7.4-alpine` service container |
| App | uvicorn, **1 worker** (2+ workers would give each process its own fakeredis and contaminate the warm cell — documented finding) | uvicorn, 1 worker |
| Corpus | 150 realistic + 20 000 `perf-*` synthetic = **20 150 rows**, `VACUUM ANALYZE`d | same seed scripts + mandatory `ANALYZE` |
| Rate limit | `RECOMMEND_RATE_LIMIT_PER_MINUTE=0` (documented load-test switch, `config.py:95`) | same |

## 2. End-to-end HTTP cells (local iteration — not contract evidence)

`backend/scripts/load_recommend.py` — 250 samples/cell, concurrency 20, 0 errors in 500 requests.
Raw: `docs/agent-reports/stage2-evidence/t-2.2-p95/raw/load-recommend-local.{json,log}`

| Cell | n | mean | p50 | p95 | p99 | max | errors | Gate math (p95 < 2000 ms) |
|---|---|---|---|---|---|---|---|---|
| **Cold** (unique payload per request → guaranteed cache miss) | 250 | 1124.6 | 1168.1 | **1481.8** | 1536.2 | 1570.9 | 0 | **pass, 25.9 % headroom** |
| **Warm** (identical payload, primed once → cache hit) | 250 | 84.5 | 83.0 | **119.7** | 131.7 | 137.4 | 0 | **pass, 94.0 % headroom** |

Serial (concurrency-free) cold latency is ~132 ms (§5); the cold-cell values above are throughput-bound queueing on 2 vCPU at concurrency 20 — i.e. this is the *pessimistic* shape of the gate, and it still passes.

## 3. DB-level fused `<=>` query (bench_pgvector.py, 20 150 rows)

Raw: `…/raw/bench-local-20150-analyzed.{json,log}` · plan: `…/raw/ef-search-sweep-local.log`

- Cold p95 **11.6 ms** / warm p95 **10.1 ms** over 56 fused queries (8 quizzes × 7 categories); no-result query 0.5 ms.
- `EXPLAIN (ANALYZE, BUFFERS)` at the production `SET LOCAL hnsw.ef_search = 400`: **Bitmap Index Scan on `ix_products_category` → filter → top-N heapsort**, 16.4 ms, 100 rows. The planner deliberately skips the HNSW index at this catalog shape: category selectivity (~4.1 k rows/category) makes the exact top-N sort cheaper than an ANN walk + post-filter. That is a *cost-based exact* plan, not a defect — recall is 1.0 by construction.

### Measurement-artifact finding (MANDATORY for the CI job)

After `seed_perf_products.py` bulk-inserts 20 k rows, planner statistics are stale (estimate was 564 rows vs 20 150 actual) and the HNSW probe degraded to a Seq Scan (37 ms). **`VACUUM ANALYZE products` after seeding is required** — with fresh stats the probe uses the index (1.6 ms @ ef=40). The staged CI p95 job runs `ANALYZE` post-seed for this reason. This is a measurement artifact, not a schema defect.

## 4. `hnsw.ef_search` sensitivity (T-2.2 tuning check)

`backend/scripts/ef_search_sweep.py`, raw: `…/raw/ef-search-sweep-local.{json,log}` — 48 samples/setting, recall vs forced-exact scan:

| ef_search | lat p50 | lat p95 | recall@100 (mean/min) |
|---|---|---|---|
| 100 | 9.95 ms | 12.00 ms | 1.0 / 1.0 |
| 200 | 10.25 ms | 13.13 ms | 1.0 / 1.0 |
| **400 (configured)** | 9.57 ms | 11.55 ms | 1.0 / 1.0 |
| 800 | 9.62 ms | 12.06 ms | 1.0 / 1.0 |

**Verdict: no tuning applied.** ef_search is plan-inert at this catalog shape (the fused query's plan is exact, see §3), and latency is flat across the sweep. The configured 400 stays (config-versioned in `ai/recommender_config.json`, `stage_b.hnsw_ef_search`); it becomes load-bearing only when the catalog grows enough for the planner to choose the ANN path, where a high ef guards recall. Changing it now would be exactly the speculative micro-optimization invariant 2 forbids.

## 5. Cache hit path

Raw: `…/raw/cache-hit-path-local.log` — same user, identical payload ×3: **132 ms (miss) → 21 ms → 22 ms (hits)**, responses carry `meta.weights_profile/current` + version stamps. Cache-key scoping and single-flight semantics are covered by `tests/test_perf_v2.py` (10/10, see T-2.3). Real-Redis verification belongs to the CI cell (§7) — fakeredis hit numbers are indicative only.

## 6. SA-7 methodology notes

- Percentiles: nearest-rank on the sorted sample; units ms throughout; n stated per cell; failures counted, none dropped (0/500).
- Cold-cell validity: uniqueness of `rec:{user}:{sha}` guaranteed by distinct payloads (37/23-cycle dimensions + 50-cycle budget + style/palette/material rotation).
- Warm-cell validity: single uvicorn worker (see §1) — with ≥2 workers each process holds a private fakeredis and the "warm" cell silently mixes misses.
- One prior bench run (pre-`ANALYZE`) is retained unedited (`raw/bench-local-20150.{json,log}`) as the record of the stale-stats artifact; the corrected run is a separate file, not an overwrite.

## 7. CI measurement (evidence of record) — pending

The staged `ci/ci.stage2.yml` adds a dedicated `p95-evidence` job (pgvector + `redis:7.4-alpine` services, seed → `ANALYZE` → cold+warm ≥200 samples/cell via `load_recommend.py`, `EXPLAIN ANALYZE` + raw JSON uploaded as artifacts). This section will carry the CI tables and the final contract verdict once the human supervisor activates the staged workflow (hand-off note §H-2 in the Stage-2 report). Until then the gate is **NOT CLAIMED** — local evidence above says the pass is expected, not proven.
