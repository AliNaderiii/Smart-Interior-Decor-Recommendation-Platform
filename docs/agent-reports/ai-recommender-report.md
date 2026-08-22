# Stage 04 — AI Recommender, Extraction & Data Quality Report

Date: 2026-08-21 (UTC) · Branch: `arena/01a02613-smart-interior-decor-recommend`
Base commit: `a07f0145fed320949f41ee67a020ad3e98f3aff0` (= remote `v2-strict-mode`)
Governing prompts: `agent-master-prompts/00-README.md`, `04-ai-recommender-data.md`
Supervisor: ML/AI Lead (virtual team; every change and evidence file reviewed before commit).

> **Branch-name note (same pattern as prior stages):** Master Prompt 04
> specifies `agent/ai-recommender-2026-08-21`. That branch exists on the
> remote at the base commit `a07f014`; this session's environment is
> hard-bound to `arena/01a02613-smart-interior-decor-recommend` (also at
> `a07f014`). The tree produced is what the agent branch would carry; the
> integration manager (Prompt 10) can fast-forward it. No other branch was
> created, modified, merged, rebased, reset, force-pushed or cherry-picked.

## Decision

**CONDITIONAL PASS.** Everything executable in this environment was executed
against real services and passed: full suite on real PostgreSQL 16.2 +
pgvector 0.6.2 and real Redis 6.2.14 (476/476), SQLite suite green (463
passed / 13 service-gated skips), 30/30 recommender acceptance scenarios
(DoD ≥ 28/30), 18/18 harness scenarios, pgvector plans/p95/recall evidence
at 1k and 11k rows, and the production fail-closed embedding policy.
The condition: **the real vision-model benchmark and real CLIP verification
are BLOCKED** (no provider keys; HuggingFace egress refused) — recorded with
exact commands in the evidence, never simulated, and every affected quality
claim stays behind the human-review gate. Per the DoD, "real extraction meets
the 80% criterion **or is transparently blocked behind human review**" — the
latter holds.

## What was built

### 1. AI version registry (`backend/ai/model_registry.py`)
Single source of truth: extraction provider/model/prompt version, taxonomy
version, embedding model + dim, recommender config version. Stamped into
extraction results (`extraction_raw`), recommendation payloads (`meta`) and
every evidence artifact. Closes the "unversioned AI stack" risk (AI-05).

### 2. Taxonomy module (`backend/ai/taxonomy.py` + `seed_data/style_taxonomy.json` 2.1)
Stable IDs (unchanged from 2.0), mandatory Persian labels, **new** patterns
and categories sections with Persian labels (previously the pattern
allowlist existed only inside the extractor), an explicit unknown-value
policy (fa+en), `clamp_to_taxonomy` (discard-and-report, never guess), and
integrity validation. Quiz schema now validates patterns against the
taxonomy and colors as `#RRGGBB`, and budget fields are bounded to the PG
int4 ceiling.

### 3. Extraction hardening (`backend/ai/feature_extractor.py`, `ai/extraction_review.py`)
SSRF guard with per-hop revalidation on the image fetch (**closes
IR-SEC-003 / D-03**), version stamps on every result, explicit review gate
(auto-accept ≥ 0.80; `needs_review` + machine-readable reasons), and failure
behaviour that **never fabricates**: production failures store empty flagged
features for human review; dev fallback is labelled `mock-fallback`,
capped at 0.30 confidence.

### 4. Embedding safety (`backend/ai/embedding_service.py`)
Production raises `EmbeddingBackendError` on CLIP-unavailable **and** on a
configured `hash` backend (previously a silent downgrade with a log line).
`verify_embedding()` (dim / unit-norm / NaN) and
`validate_embedding_runtime()` (startup hook, IR-AI-001) added;
`--from-json` seeding without the real-vectors file now exits loudly
(load_realistic_products.py).

### 5. Recommender audit (`backend/app/services/recommender.py`, `ai/recommender_config.json`)
Weights/knobs moved to a versioned, validated config with an explicit
`weights_source: heuristic (ADR-005), learned_from_data: false`. Deterministic
tie-breaking by stable product id at **every** sort including the SQL
`ORDER BY`. No-result/few-result: `meta.empty_categories`, budget echo,
never pad past hard filters. Duplicate suppression (normalized title +
embedding cosine ≥ 0.995) and per-style cap. Explanation fidelity locked by
tests that recompute `final_score` from explanation × weights on every
returned item.

### 6. Evaluation framework
- `scripts/evaluate_extraction.py`: per-feature micro P/R/F1, confidence
  calibration (buckets + ECE), latency percentiles, failure rate,
  review rate, cost estimate, MOCK/REAL labelling in every artifact,
  `--images-dir` for real pixels, `--json` output.
- `scripts/evaluate_recommender.py`: 18-scenario deterministic harness
  (tie-break, no-result, diversity, fidelity, feedback, edges) with JSON
  evidence output.
- `scripts/seed_catalog_scale.py`: deterministic ≥1k/10k synthetic Persian
  catalog for pgvector benchmarks.
- `scripts/bench_pgvector.py`: EXPLAIN (ANALYZE, BUFFERS), cold/warm p50/p95,
  recall vs exact scan, no-result latency, HNSW/ef_search probe.

### 7. Tests (new files only; all pre-existing suites untouched except the
two disclosed fixture updates)
`test_ai_taxonomy.py` (16), `test_embedding_guards.py` (14),
`test_extraction_review.py` (13), `test_recommender_v2.py` (23),
`test_recommender_redis_real.py` (5, real-Redis-gated),
`test_pgvector_real.py` (9, real-PG-gated, dedicated DB + migration
round-trip).

## Verification (all executed here)

| Gate | Command (abbrev.) | Result |
|---|---|---|
| SQLite suite | `pytest tests/ --ignore=tests/test_pgvector_real.py` | **463 passed, 13 skipped, exit 0** |
| Real PG+pgvector+Redis suite | `DATABASE_URL=…pgvector… REDIS_URL=… TEST_REDIS_URL=… pytest tests/ --ignore=tests/test_pgvector_real.py` | **476 passed, exit 0** |
| pgvector module (dedicated DB) | `TEST_DATABASE_URL=… pytest tests/test_pgvector_real.py` | **9 passed** |
| Acceptance | `pytest tests/test_recommender.py` | **30/30** (DoD ≥ 28/30) |
| Scenario harness | `python scripts/evaluate_recommender.py` | **18/18**, exit 0 |
| MOCK benchmark | `AI_PROVIDER=mock python scripts/evaluate_extraction.py` | exit 0, **labelled MOCK**, 100% harness baseline |
| REAL benchmark | `AI_PROVIDER=gemini GEMINI_API_KEY= … --real` | **BLOCKED** (no key) — exact command + error captured |
| Real CLIP | `pip install torch sentence-transformers` (OK) → `SentenceTransformer("clip-ViT-B-32")` | **BLOCKED** (huggingface.co egress 000) |
| Bench 1k / 11k | `scripts/bench_pgvector.py` | filtered p95 0.9 / 6.7 ms warm; recall 1.000; HNSW probe: ef40 → 40/100 rows, ef400 → 100/100 |
| App-level 11k | inline probe (evidence 10) | cold p95 227 ms, warm p95 2 ms |
| Lint | `ruff check app ai scripts tests` | **All checks passed** |
| Secret scan | `python scripts/audit_secrets.py` | 0 findings (run again post-commit) |
| Doc links | `python scripts/audit_docs_links.py` | 0 broken (run again post-commit) |

Evidence: [`ai-recommender-evidence/`](ai-recommender-evidence/README.md).
Detailed analysis: [`docs/ai/evaluation-report.md`](../ai/evaluation-report.md).

## Honest-results ledger (what is real, what is mock, what is blocked)

| Claim class | Status |
|---|---|
| Vision-model extraction accuracy | **UNKNOWN — BLOCKED.** MOCK 100% is a harness baseline and is labelled as such in stdout, JSON and reports |
| Real CLIP embeddings in the catalog | **NOT PRESENT.** Catalog vectors in this sandbox are hash (dev/test); production path fail-closed and tested |
| pgvector / PostgreSQL / Redis behaviour | **REAL** (embedded pgserver 16.2 + pgvector 0.6.2, redislite 6.2.14 — real protocol servers, not emulators; not Docker) |
| Latency numbers | REAL on the declared sandbox environment; staging hardware will differ |
| Recommender weights | heuristic, explicitly not learned |
| Feedback re-rank | bounded heuristic; no trained recommender exists or is claimed |

## Remaining risks (from `docs/ai/risk-register.md`)

- **AR-1** real vision quality unknown until a key + licensed image set exist;
  human review is the default gate — not a quality claim.
- **AR-2** production needs the CLIP bootstrap runbook executed on an
  egress-enabled machine (`embeddings_real.json`); until then prod boot with
  seeding fails by design (IR-AI-003).
- **AR-3** p95 measured on sandbox; staging rerun required.
- **AR-4** feedback stays heuristic until ~10k events + an offline eval set.
- **AI-12 residual**: HNSW-vs-exact planner choice is size/shape-dependent —
  the ef_search=400 knob is validated and necessary when ANN is chosen.
- Sanctions/egress legality of US AI providers for a Persian catalog is an
  open product-owner decision (`docs/ai/privacy-cost-assessment.md` §2).

## Integration requests

IR-AI-001 (startup embedding check, HIGH), IR-AI-002 (admin review queue,
MEDIUM), IR-AI-003 (prod compose seeding vs real embeddings, HIGH),
IR-AI-004 (retired `GEMINI_MODEL` default, HIGH), IR-AI-005 (real-service AI
modules in CI, MEDIUM), IR-AI-006 (feedback_events, LOW) — full texts and
the two disclosed cross-stage test-fixture updates are appended to
`integration-request.md`.

## Commit sequence

Atomic commits on this branch (see `git log`): taxonomy + registry; extractor
+ review gate; embedding safety; recommender engine + config; schemas;
evaluation scripts; tests; docs + evidence; integration requests. Each commit
message states its single logical topic and the verification that accompanies
it.
