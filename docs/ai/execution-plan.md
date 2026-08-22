# Stage 04 — Execution Plan (AI Recommender, Extraction & Data Quality)

Branch: `arena/01a02613-smart-interior-decor-recommend` (session-bound; logical
stage branch `agent/ai-recommender-2026-08-21` exists on the remote at the same
base commit — integration via Prompt 10).
Base commit: `a07f0145fed320949f41ee67a020ad3e98f3aff0` (= remote `v2-strict-mode`).
Date: 2026-08-21 (UTC). Supervisor: ML/AI Lead (reviews every change and evidence
file before commit).

## 0. Verified starting state

| Check | Result |
|---|---|
| `git merge-base` with base commit | branch created from `a07f014` — verified |
| Baseline backend suite (SQLite + fakeredis) | **392 passed, 8 skipped, exit 0** (`pytest tests/ -p no:warnings`) |
| AI credentials in sandbox | none (`GEMINI_API_KEY` / `OPENAI_API_KEY` unset) → real-model benchmark will be **BLOCKED**, never fabricated |
| Real PostgreSQL/pgvector available | yes, via `pgserver` (PostgreSQL 16.2 + pgvector 0.6.2), same evidence class as Stage 07 |
| Real Redis available | yes, via `redislite` 6.2.14 |
| CLIP runtime (`sentence-transformers`+`torch`) | not installed by default; real-CLIP verification attempted separately and recorded as PASS/BLOCKED with exact commands |

## 1. Ownership map

| Zone | Owner | Action here |
|---|---|---|
| `backend/ai/**` | this stage | modify/extend |
| `backend/app/services/recommender.py` | this stage | modify |
| `backend/app/schemas/quiz.py` (+ product schemas where directly required) | this stage (tests included) | add taxonomy validation (patterns/colors) |
| `backend/scripts/{seed,eval,bench}*` | this stage | extend/add |
| `backend/seed_data/style_taxonomy.json` | this stage (seed data) | add patterns/categories sections |
| `docs/ai/**`, `docs/agent-reports/ai-*` | this stage | create |
| `integration-request.md` | shared ledger (append-only section) | append Stage 04 requests |
| `backend/app/core/config.py`, `app/main.py`, `app/api/routes/*`, alembic migrations, frontend, compose | **other owners** | integration requests only |

## 2. Workstreams

1. **AI version registry** — `backend/ai/model_registry.py`: one source of truth
   for extraction provider/model/prompt version, taxonomy version, embedding
   model + dimensions, recommender config version. Stamped into extraction
   results, recommendation payloads and evidence.
2. **Taxonomy module** — `backend/ai/taxonomy.py` + `seed_data/style_taxonomy.json`
   extension (patterns + categories with Persian labels, stable IDs, explicit
   unknown-value policy). Integrity tests; unknown values rejected at schema and
   clamped at extraction.
3. **Extraction hardening** — SSRF guard (closes IR-SEC-003 within this stage's
   ownership), provider/model/prompt/taxonomy stamps, review gate
   (`needs_review` + reasons) with confidence thresholds, and failure behaviour
   that never fabricates features in production.
4. **Embedding safety** — production refuses silent hash fallback
   (`EmbeddingBackendError`), `validate_embedding_runtime()` for startup,
   dimension/normalization verification helper, re-embedding strategy documented.
5. **Recommender audit** — versioned `recommender_config.json` (weights, source,
   feedback and diversity knobs) validated at import; deterministic tie-breaking
   everywhere; no-result/few-result meta; duplicate suppression + style
   diversification; explanation fidelity locked by tests.
6. **Evaluation framework** — upgraded 50-image benchmark (per-feature
   precision/recall, calibration, latency, cost, failures; MOCK vs REAL labels),
   recommender scenario harness, pgvector benchmark at 150/1k/10k rows with
   EXPLAIN ANALYZE and p95.
7. **Real-service evidence** — full suite + new tests against real
   PostgreSQL/pgvector and real Redis; query plans and latency captured.
8. **Feedback-event design** — documented schema for like/dislike/click/save
   without claiming a trained feedback recommender exists.
9. **Privacy & cost assessment** — provider data-flow, retention, egress
   considerations for a Persian catalog, per-call and monthly cost model.
10. **Docs, reports, IRs, atomic commits, PR** targeting `v2-strict-mode`.

## 3. Definition of Done (from Master Prompt 04)

- ≥ 28/30 recommender acceptance scenarios pass (evidence captured).
- Real extraction meets the 80% criterion **or is transparently BLOCKED behind
  human review** — never fabricated.
- p95 measured on a declared environment at ≥ 1k and 10k synthetic rows.
- No silent fallback, no fabricated explanations.
- Existing tests stay green; changed files pass ruff; no secrets committed.

## 4. Sequencing

1. Plan + risk register (this file + `docs/ai/risk-register.md`).
2. Code: model registry → taxonomy → extractor → embeddings → recommender → schemas.
3. Scripts: evaluation, recommender harness, catalog seeder, pgvector bench.
4. Tests (new files only; existing suites untouched).
5. Evidence runs: SQLite suite, mock benchmark, real PG/Redis suite, plans/p95.
6. Docs: evaluation report, model versions, taxonomy, config, privacy/cost,
   feedback events; agent report + evidence dir; integration requests.
7. Review diff (ML/AI Lead), atomic commits, push, PR — do not merge.
