# MASTER PROMPT 04 — Recommendation Engine, AI Extraction & Data Quality

## Mission
Make recommendation quality measurable, deterministic where required, explainable and safe for a real interior-decoration catalog.

## Mandatory virtual team
Delegate to: ML/AI Lead (manager), recommender-systems engineer, computer-vision/LLM engineer, data engineer, interior-design taxonomy expert, MLOps engineer, performance engineer and evaluation QA.

## Allowed scope
`backend/ai/**`, `backend/app/services/recommender.py`, product/quiz schemas and tests where directly required, seed/evaluation scripts, `docs/ai/**`, `docs/agent-reports/ai-*`. Coordinate migrations through `integration-request.md`; do not redesign portals.

## Work
1. Specify taxonomy for living-room products, styles, colors, materials, patterns, dimensions, room type and unknown values; preserve Persian labels and stable IDs.
2. Audit the three-stage pipeline: hard filters, pgvector retrieval and weighted scoring. Make weights/configuration explicit, validated, versioned and observable.
3. Define deterministic tie-breaking, no-result/few-result behavior, diversity rules, duplicate suppression and category quotas.
4. Preserve explanation fidelity: every displayed match must correspond to actual score components; never invent reasons.
5. Run the 50-image benchmark against the real provider selected for staging. Report per-label precision/recall, confidence calibration, latency, cost, failures and mock-vs-real separation.
6. Enforce human review for low-confidence/failed extraction; store model, prompt, taxonomy and extraction version.
7. Ensure embeddings are real in Production, dimension-compatible, normalized and never silently replaced by hash fallback. Add re-embedding/version migration strategy.
8. Test pgvector query plans and p95 using realistic catalog sizes (at least 1k and synthetic 10k), cold/warm cache, multi-worker Redis and no-result cases.
9. Add feedback event design for like/dislike/save/click, but do not pretend it is already a trained recommender.
10. Audit privacy/cost risks in sending images or user answers to external providers; redact and document retention.

## Required evidence
`docs/ai/evaluation-report.md`, fixtures with ground truth, score breakdown examples, benchmark commands/raw summaries, query plans, cost estimate and residual limitations.

## DoD
At least 28/30 agreed recommender scenarios pass; real extraction meets the contracted 80% criterion or is transparently blocked behind human review; p95 target is measured on a declared environment; no silent fallback or fabricated explanation.

## Parallel protocol
Branch `agent/ai-recommender-<date>`. Avoid shared migrations and README. Record requests for integration rather than touching other ownership zones.
