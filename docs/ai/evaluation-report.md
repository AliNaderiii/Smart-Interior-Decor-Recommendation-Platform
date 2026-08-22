# AI Evaluation Report — Extraction & Recommendation (Stage 04)

Branch: `arena/01a02613-smart-interior-decor-recommend` · Base: `a07f014` (`v2-strict-mode`) · Date: 2026-08-21 (UTC)
Owner: Master Prompt 04 (AI Recommendation Engine, Data Quality & MLOps).
Evidence index: [`../agent-reports/ai-recommender-evidence/`](../agent-reports/ai-recommender-evidence/README.md)

> **Read this first.** This report separates three evidence classes everywhere:
> **MOCK** (deterministic filename heuristic — a harness baseline, never a
> vision-model accuracy claim), **LOCAL** (real PostgreSQL 16.2 + pgvector
> 0.6.2 via pgserver and real Redis 6.2.14 via redislite in this sandbox), and
> **BLOCKED** (could not be executed here; exact command and unblock path
> recorded). No number below is extrapolated from another environment.

---

## 1. Executive summary

| Question | Answer |
|---|---|
| 50-image benchmark, REAL provider | **BLOCKED** — no `GEMINI_API_KEY`/`OPENAI_API_KEY` in the sandbox (`02-real-provider-benchmark-BLOCKED.log`). Quality of the real vision model remains **unknown and unclaimed**. |
| 50-image benchmark, MOCK | 100.0% harness baseline, labelled MOCK in stdout/JSON/report (`01-mock-extraction-benchmark.log`, `mock-extraction-report.json`) |
| Real CLIP embeddings | Runtime installable (torch 2.13.0, sentence-transformers 6.0.0 from PyPI) but **model download BLOCKED** — huggingface.co egress refused (`03-clip-verification-BLOCKED.log`). Production guard against silent hash fallback implemented and tested instead. |
| Real PostgreSQL + pgvector | **LOCAL PASS** — 476/476 tests, migration chain, HNSW index, dimension guard, deterministic order, recall 1.0 |
| Real Redis | **LOCAL PASS** — 8 shared-store tests + 5 recommender-cache tests (TTL, per-user keys, feedback invalidation) |
| p95 at catalog scale | Filtered Stage A+B query: **0.9 ms @ 1k rows, 6.7 ms @ 11k rows** (warm, DB-level). App-level `/recommend` on 11k rows: **227 ms cold / 2 ms cached** p95. Budget: 2000 ms. |
| Recommender acceptance | **30/30** pytest scenarios (`07-acceptance-30-scenarios.log`; ≥28/30 required) + **18/18** harness scenarios (`08-recommender-scenario-harness.log`) |
| Silent fallbacks | Eliminated and test-locked: production hash embeddings raise; production extraction failure stores empty flagged features; `--from-json` without the file exits loudly |

## 2. Version stamps (all results below carry these)

From `ai/model_registry.py` (single source of truth, stamped into extraction
results, recommendation payloads and every evidence artifact):

| Artefact | Version |
|---|---|
| AI stack | `2026-08-21.1` |
| Extraction prompt | `p2` (taxonomy-driven pattern list, review fields) |
| Taxonomy | `2.1` (additive: +patterns, +categories, +unknown-value policy; style IDs unchanged from 2.0) |
| Embedding model | `clip-ViT-B/32`, 512-d, unit-norm (hash fallback labelled `DETERMINISTIC FALLBACK — NOT a semantic model`) |
| Recommender config | `2026-08-21.1` (`ai/recommender_config.json`, weights source: heuristic ADR-005, **not learned**) |
| Review gate | auto-accept ≥ 0.80; fallback cap 0.30 (`ai/extraction_review.py`) |

## 3. Extraction benchmark (50 images)

### 3.1 MOCK run (executed)

```
$ cd backend && AI_PROVIDER=mock python scripts/evaluate_extraction.py \
      --json docs/agent-reports/ai-recommender-evidence/mock-extraction-report.json
MODE             : MOCK   ** NOT a vision-model accuracy claim **
images evaluated : 50          mean accuracy: 100.0%
style micro P/R/F1     : 1.000 / 1.000 / 1.000
material micro P/R/F1  : 1.000 / 0.500 / 0.667
calibration ECE  : 0.1000   latency p50/p95: 0 / 0 ms
failures         : 0/50     needs review: 0/50 (0%)   cost: $0 (no external calls)
```

Interpretation — the mock reads keywords out of the fixture filenames, so
style is trivially recovered and materials that exist only in the pixels
(e.g. fabric on a wooden frame) are missed: material **recall 0.500**. This is
the expected signature of a harness baseline and precisely why it must never
be quoted as model accuracy. Calibration gap (ECE 0.10) exists because the
heuristic always self-reports 0.9 confidence.

The committed fixture carries synthetic URLs (`images.smartdecor.dev`) with
human ground truth. A REAL run additionally needs actual pixels
(`--images-dir DIR` with `{id:02d}-*.jpg`) — see the script docstring.

### 3.2 REAL runs (BLOCKED — not executed, not simulated)

```
$ AI_PROVIDER=gemini GEMINI_API_KEY= python scripts/evaluate_extraction.py --real
ERROR: --real requires AI_PROVIDER=gemini|openai and the matching API key in the environment.
Blocked command was: AI_PROVIDER=gemini GEMINI_API_KEY=<empty> OPENAI_API_KEY=<empty> ...
```

Unblock path: provision the key → document authorization per
[`privacy-cost-assessment.md`](privacy-cost-assessment.md) §4 → supply real
benchmark images → rerun with `--real --sample 5` first (cost control). The
contracted bar (mean ≥ 0.80 in REAL mode) then applies; below it, every
low-confidence extraction stays behind the human-review gate by construction.

**Operational finding (MLOps):** the configured default `GEMINI_MODEL=
gemini-2.0-flash` refers to a model Google shut down on 2026-06-01; the
price-equivalent replacement is `gemini-2.5-flash-lite`. Config default and
`.env.example` are owned by other stages → **IR-AI-004**.

## 4. Embedding safety and verification

| Check | Result | Evidence |
|---|---|---|
| Production refuses CLIP-unavailable | PASS — `EmbeddingBackendError` raised | `tests/test_embedding_guards.py` |
| Production refuses configured `hash` | PASS — same error, policy-documented | idem |
| Development falls back **labelled** | PASS — backend `hash`, model string says `NOT a semantic model` | idem |
| Dimension check | PASS — `verify_embedding` catches 511/513-dim | idem |
| Unit-norm check | PASS — catches scaled vectors (‖v‖≠1) | idem |
| NaN/None guards | PASS | idem |
| pgvector column dimension | PASS — `vector(512)` from migration `0001`; wrong-dim insert rejected by DB | `tests/test_pgvector_real.py` |
| Catalog embeddings 512-d + unit-norm | PASS — 100/100 seeded products | scenario 17, `recommender-scenarios.json` |
| Real CLIP forward pass | **BLOCKED** (huggingface.co egress) | `03-clip-verification-BLOCKED.log` |
| Re-embedding strategy | documented | [`model-versions.md`](model-versions.md) §3 |

## 5. Recommendation engine audit

### 5.1 Pipeline stages (as measured on real PG)

Stage A (hard filter: room_type + category + budget + verified) and Stage B
(pgvector cosine retrieval) run as one fused query; Stage C weights the
candidates with full explanation; Stage D applies bounded feedback re-rank and
diversity. Weights live in `ai/recommender_config.json` with an explicit
`weights_source` record — heuristic (ADR-005), **not learned from data** — and
are validated at import (keys, ranges, sum-to-1, version match). Every result
payload carries `meta.weights_version` so a displayed explanation can always
be audited against the weights that produced it.

### 5.2 Determinism, no-result, diversity (executed)

| Behaviour | Result | Where proven |
|---|---|---|
| Deterministic tie-breaking (SQL, Stage B/C, feedback) by stable product id | PASS | `test_recommender_v2.py`, pg `test_fused_query_is_deterministic_across_runs`, scenarios 05/06 |
| Byte-identical ordering across identical runs | PASS | scenario 05 |
| No-result: empty categories reported in `meta.empty_categories`, nothing padded | PASS | scenarios 03/13/14, `test_impossible_budget_reports_all_categories_empty` |
| Out-of-budget items never returned (incl. min-budget edge) | PASS | scenarios 02/04, `test_out_of_budget_never_recommended` |
| Duplicate suppression (normalized title, embedding cosine ≥ 0.995) | PASS | scenario 10, `test_exact_duplicate_titles_suppressed` |
| Style cap (`max_per_style` 4 of 5) | PASS | scenario 11 |
| Explanation fidelity — final = Σ wᵢ·componentᵢ (±0.02) | PASS on every returned item | scenario 08 (35 items), `test_every_explanation_reconstructs_final_score` |
| `matched_materials` equals the real intersection | PASS | scenario 09 (28 entries) |
| Feedback thumbs-down demotes (bounded heuristic, cache identity includes feedback) | PASS | scenario 15, `test_feedback_signal_changes_cache_identity` (real Redis) |
| Unknown pattern/color rejected at schema (422, taxonomy in the error) | PASS | scenario 18, `test_ai_taxonomy.py` |
| Budget fields bounded to int4 range (2e9) | PASS | `app/schemas/quiz.py` (added this stage) |

### 5.3 Performance & query plans (LOCAL, real PostgreSQL 16.2 + pgvector 0.6.2)

Environment: pgserver embedded PG on a 2 vCPU/3.8 GiB sandbox; deterministic
synthetic catalogs from `scripts/seed_catalog_scale.py`; DB-level latencies
from `scripts/bench_pgvector.py` (`09-bench-pgvector.log`, JSON artifacts).
Declared environment caveat: this is **not** staging hardware; absolute
numbers will differ, the *shape* of the findings is what transfers.

| Metric | 1,000 rows | 11,000 rows (1k+10k synthetic) |
|---|---|---|
| Stage A+B filtered query, cold p50/p95 | 1.0 / **1.7 ms** | 6.3 / **7.1 ms** |
| Stage A+B filtered query, warm p50/p95 | 0.9 / **0.9 ms** | 6.2 / **6.7 ms** |
| Planner choice for the filtered query | Bitmap Heap Scan on `ix_products_category` + exact Sort | same |
| Recall vs exact scan (sofa, LIMIT 100) | 1.000 | 1.000 |
| Candidates surviving to Stage C | 100/100 | 100/100 |
| No-result query (impossible budget) | 0.6 ms | 0.8 ms |
| HNSW probe (unfiltered ORDER BY) | planner prefers exact scan at this size (legitimate: cheaper, recall 1.0) | **HNSW index scan used**; `ef_search=40` → **40/100 rows returned (truncation!)**, `ef_search=400` (configured) → 100/100 @ 5.0 ms |
| App-level `/recommend` (7 categories) | — | cold p95 **227 ms**, warm (Redis) p95 **2 ms** (`10-app-level-latency-11k.log`) |

Two conclusions worth naming:

1. **The planner is smarter than the index, happily.** For the *filtered*
   production shape at these catalog sizes, an exact bitmap+sort beats
   post-filtered ANN — so we get exact results (recall 1.0) at 7 ms p95. The
   HNSW index exists, is valid, and the `hnsw.ef_search=400` configuration is
   load-bearing the moment the planner *does* pick it: the probe at 11k rows
   shows the pgvector default 40 truncating results to 40 of the requested
   100 — the same silent recall loss V2 Phase 2 measured at 20.7k rows.
2. **The 2 s budget has ~9× headroom cold** at 11k rows on *sandbox*
   hardware; the cache collapses it to ~2 ms.

## 6. Test-suite status (all executed in this sandbox)

| Suite | Environment | Result |
|---|---|---|
| Full backend suite | SQLite + fakeredis (CI default) | **463 passed, 13 skipped, exit 0** (`04-sqlite-suite.log`) |
| Full backend suite | real PG 16.2 + pgvector 0.6.2 + real Redis 6.2.14 | **476 passed, exit 0** (`05-pg-redis-parity-suite.log`) |
| `tests/test_pgvector_real.py` (dedicated DB, migration round-trip, HNSW index, dim guard, recall, determinism) | real PG | **9 passed** (`06-pgvector-real-tests.log`) |
| Recommender acceptance `tests/test_recommender.py` | SQLite | **30/30** (`07-acceptance-30-scenarios.log`; DoD ≥28/30) |
| Scenario harness `scripts/evaluate_recommender.py` | SQLite + hash | **18/18** (`08-recommender-scenario-harness.log`) |
| Mock extraction benchmark | mock | exit 0, labelled MOCK |

Skips in the SQLite run are the service-gated modules (real-Redis ×13
including this stage's 5) — they all run in the parity invocation.

## 7. Limitations (explicit)

1. **Real vision-model quality is unknown.** MOCK ≠ accuracy; nothing in this
   report claims otherwise. Until the REAL benchmark runs, *every* extraction
   lands behind the human-review gate unless a provider returns ≥0.80
   confidence — and even then `is_verified` requires an admin.
2. **p95 numbers are sandbox-shaped** (2 vCPU pgserver, redislite, no network
   hops). Staging must re-run `scripts/bench_pgvector.py`.
3. **Hash embeddings in benchmarks** make the perf runs hermetic; they do not
   exercise CLIP's geometry (irrelevant for planner/latency behaviour, stated
   for honesty).
4. `GEMINI_MODEL` default points at a retired model (IR-AI-004); until it is
   updated, a first REAL run may fail with a model-not-found error — the
   failure is loud, not silent.
5. Calibration metrics for the mock measure the *harness*, not a model; ECE
   for a real provider is meaningful, for the mock it is a sanity check.

## 8. Reproduction

```bash
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.lock.txt

# 1. suite (SQLite)            -> 463 passed, 13 skipped
.venv/bin/python -m pytest tests/ --ignore=tests/test_pgvector_real.py -p no:warnings --tb=no

# 2. mock benchmark (labelled) -> MOCK baseline 100%
AI_PROVIDER=mock .venv/bin/python scripts/evaluate_extraction.py

# 3. scenario harness          -> 18/18
.venv/bin/python scripts/evaluate_recommender.py

# 4. real PG + pgvector + real Redis (services required; see scripts/dev_postgres.py)
DATABASE_URL=postgresql+psycopg://... REDIS_URL=redis://... TEST_REDIS_URL=redis://... \
  .venv/bin/python -m pytest tests/ --ignore=tests/test_pgvector_real.py -p no:warnings
DATABASE_URL=postgresql+psycopg://.../ai_test TEST_DATABASE_URL=... \
  .venv/bin/python -m pytest tests/test_pgvector_real.py -p no:warnings

# 5. scale benchmark
DATABASE_URL=postgresql+psycopg://... .venv/bin/python scripts/seed_catalog_scale.py --rows 1000
DATABASE_URL=postgresql+psycopg://... .venv/bin/python scripts/bench_pgvector.py --sizes 1000
# repeat with --rows 10000 / --sizes 10000
```
