# Recommender Configuration & Weights — provenance and rules

Owner: Master Prompt 04. Config: `backend/ai/recommender_config.json`
(`config_version: 2026-08-21.1`). Loader/validator:
`app/services/recommender.py::load_recommender_config` (runs at import,
fail-fast).

## 1. Weights and their source (explicit)

```json
"weights": { "style": 0.30, "color": 0.30, "budget": 0.20,
             "material": 0.15, "pattern": 0.05 }
```

**Source: heuristic, from ADR-005 (docs/ARCHITECTURE.md). NOT learned from
data.** No interaction dataset exists to learn from, and the config says so
structurally (`weights_source.learned_from_data: false`). The reasoning:
style and colour dominate interior-design preference; budget is a strong
practical filter; material is secondary; pattern is a tiebreaker. The precise
split is expert judgement, and any change must:

1. bump `config_version` **and** `ai.model_registry.RECOMMENDER_CONFIG_VERSION`
   together (the loader refuses a mismatch);
2. re-run `tests/test_recommender.py` (30 acceptance scenarios, ≥28/30) and
   `scripts/evaluate_recommender.py` (18/18) — the fidelity tests recompute
   every displayed score from weights × components, so a silent weight change
   cannot ship;
3. flush `rec:*` caches (payloads embed `meta.weights_version`).

Weights are validated at import: exact key set, each in [0,1], Σ = 1 ± 1e-9.
The version is stamped into every recommendation payload
(`meta.weights_version`, `meta.weights`) so an explanation is always auditable
against the configuration that produced it.

## 2. Stage B (semantic retrieval)

| knob | value | note |
|---|---|---|
| `candidate_limit` | 100 | rows passed from pgvector to scoring |
| `hnsw_ef_search` | 400 | mirrors `settings.HNSW_EF_SEARCH`; the pgvector default 40 measurably truncates post-filtered ANN (40/100 rows at 11k in `09-bench-pgvector.log`) |

## 3. Results policy

* `min_results` 3 / `max_results` 5 per category (fewer returned when fewer
  qualify — **never padded** past the hard filters).
* `no_result_policy`: empty categories are reported in
  `meta.empty_categories`; the response always echoes the budget window.

## 4. Feedback re-rank (bounded heuristic — not a trained model)

`boost +0.12` on 👍, `penalty −0.35` on 👎 (penalty > boost because "no" is a
stronger signal than "yes"). Applied **after** explainable scoring; the
adjustment is visible as a separate `feedback` field; feedback is part of the
cache fingerprint so a thumb always changes the next response. This is a
transparent heuristic, not a learned recommender — see
[`feedback-events.md`](feedback-events.md) for the event design that could
*later* support learning.

## 5. Diversity (Stage 04)

| knob | value | meaning |
|---|---|---|
| `duplicate_title_normalized` | true | same normalized title (case/punctuation-insensitive, Persian-aware character class) kept once |
| `duplicate_embedding_cosine` | 0.995 | embedding cosine ≥ threshold counts as a duplicate listing |
| `max_per_style` | 4 | at most 4 of the ≤5 final slots share one styles-tuple |

Applied after scoring/feedback, before truncation; **membership only, never
reordering** — ranking stays score-driven and deterministic (ties break on
the stable product id at every sort, including the SQL `ORDER BY`).
