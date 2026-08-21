# AI Model & Version Registry — documentation

Owner: Master Prompt 04. Source of truth in code: `backend/ai/model_registry.py`.
This document explains *what* is versioned, *why* it matters, and the
re-embedding strategy required when any of it changes.

## 1. Stamped artefacts

| Artefact | Version / value | Where it lives | Changes require |
|---|---|---|---|
| AI stack (coarse) | `2026-08-21.1` | `ai/model_registry.py::AI_STACK_VERSION` | bump when any artefact below changes |
| Extraction provider | `mock` \| `gemini` \| `openai` | `settings.AI_PROVIDER` | config; stamped into every extraction result |
| Extraction model | e.g. `gemini-2.5-flash-lite` | `settings.GEMINI_MODEL` / `settings.OPENAI_MODEL` | config; stamped into every extraction result |
| Extraction prompt | `p2` | `ai/feature_extractor.py::EXTRACTION_PROMPT` | bump `EXTRACTION_PROMPT_VERSION`; re-run the 50-image benchmark |
| Taxonomy | `2.1` | `seed_data/style_taxonomy.json::taxonomy_version` | additive → minor bump; removing/renaming a stable ID → major bump + migration note |
| Embedding model | `clip-ViT-B/32` (512-d, unit-norm) | `ai/model_registry.py` + `ai/embedding_service.py` | **full catalog re-embedding** (§3) |
| Embedding backends | `clip` (semantic, production) / `hash` (deterministic, dev+test only) | `settings.EMBEDDING_BACKEND` | policy below |
| Recommender config | `2026-08-21.1` | `ai/recommender_config.json::config_version` | re-run acceptance scenarios + harness; update `RECOMMENDER_CONFIG_VERSION` |
| Review gate | auto-accept ≥ 0.80, fallback cap 0.30 | `ai/extraction_review.py` | stored rows are re-auditable (pure function over the payload) |

Every extraction result stores provider/model/prompt/taxonomy/needs_review in
`products.extraction_raw`; every recommendation payload carries
`meta.recommender_version`, `meta.weights_version`, `meta.embedding_backend`,
`meta.taxonomy_version`. A number without a stamp is not evidence.

## 2. Backend policy (production fail-closed)

| Environment | `EMBEDDING_BACKEND` | Behaviour |
|---|---|---|
| production | `clip` + model loadable | real CLIP vectors |
| production | `clip` + model NOT loadable | **`EmbeddingBackendError` at first embedding — boot/deploy fails loudly** |
| production | `hash` | **`EmbeddingBackendError`** — hash is a dev/test backend by policy |
| development / test | `clip` unavailable | falls back to `hash`, labelled `DETERMINISTIC FALLBACK — NOT a semantic model` |
| development / test | `hash` | deterministic hash vectors |

Rationale: hash geometry is syntactically valid but semantically meaningless;
running production ranking on it looks green while being wrong — the exact
"silent hash fallback" Master Prompt 04 forbids. The module-level guard
protects every call path; `validate_embedding_runtime()` exists for eager
startup wiring (IR-AI-001).

Seeding follows the same policy: `load_realistic_products.py --from-json`
now **exits with an error** if `seed_data/embeddings_real.json` is absent
(the base compose file passes `--from-json`), and any production-mode seeding
without real vectors fails loudly instead of writing fake geometry.

## 3. Re-embedding / version-migration strategy

Embedding identity = (model id, dimension). Both are pinned; changing either
means the old and new vectors do **not** share a space and must never be
compared. Procedure:

1. **Provision** real vectors once, on a machine with model access:
   `EMBEDDING_BACKEND=clip python scripts/seed_products.py --real-embeddings`
   → writes `seed_data/embeddings_real.json` (keyed by product title).
2. **Deploy** offline with `load_realistic_products.py --from-json`.
3. **Model change (e.g. CLIP → other, or dim change):**
   a. bump `EMBEDDING_MODEL_ID`/`EMBEDDING_DIM` in the registry **and** the
      `vector(512)` column via a new alembic migration (coordinate through an
      integration request — migrations are shared);
   b. version-stamp the new space (bump `AI_STACK_VERSION`);
   c. re-embed **all** products (`_reembed` path already exists on
      create/update) — partial re-embedding mixes spaces and silently breaks
      ranking;
   d. verify: `SELECT count(*) FROM products WHERE style_embedding IS NULL`
      must be 0 for verified products; spot-check ‖v‖=1 and dim=512
      (`ai.embedding_service.verify_embedding`);
   e. run `scripts/bench_pgvector.py` and the acceptance scenarios against the
      re-embedded catalog before switching traffic.
4. **Rollback**: keep the previous `embeddings_real.json` (git history) and
   the previous column definition; restoring is the same procedure in reverse.
5. **Quiz-side vectors** (`style_quizzes.quiz_embedding`) live in the same
   space; they are short-lived (per-quiz). Re-embedding quizzes is optional —
   stale quiz embeddings expire with the quiz, but during a transition the
   cache (`rec:*`, TTL 3600 s) must be flushed after step c.

## 4. Known drift items (integration requests)

- `GEMINI_MODEL` default is `gemini-2.0-flash`, retired by Google on
  2026-06-01 → **IR-AI-004** (config.py + .env.example owned by other stages).
- Startup does not call `validate_embedding_runtime()` yet → **IR-AI-001**
  (`app/main.py` lifespan; the module-level guard already protects every
  embedding call in the meantime).
