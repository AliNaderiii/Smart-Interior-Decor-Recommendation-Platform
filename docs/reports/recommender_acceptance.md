# Recommender Acceptance Battery — Stage 2, T-2.3

**Date:** 2026-08-27 (UTC) · **Commit under test:** `45f30c814fcd8d9e7a04f5770234b3d3e07989fc`
(= `main`/`e948b802` Stage-1 merge tree + the unchanged `ci/ci.stage2.yml` baseline copy — zero
code difference from the v0.5.0 tree).
**Owner:** SA-4 (QA Benchmark Engineer) · **Status: PASS**

---

## 1. Client-language verdict

> The contract's recommender acceptance criterion was originally phrased as **"28 of 30"
> acceptance tests passing**.

**Measured at HEAD: 30 of 30 acceptance tests pass.** In addition, all **10 of 10** performance
regression tests pass and all **18 of 18** scenario-harness checks pass — under **both**
configured weight profiles (`current` and `client-ad`). There are **no failing, skipped, or
silently-excluded cases** in the scoped battery. Zero deviations to itemize.

| Battery | Result | Evidence file |
|---|---|---|
| `tests/test_recommender.py` (the contract's "30") | **30 / 30 PASS** | `../agent-reports/stage2-evidence/t-2.3-acceptance/pytest-recommender.log` |
| `tests/test_perf_v2.py` | **10 / 10 PASS** | `…/pytest-perf-v2.log` |
| Combined verbose run (per-test names) | **40 / 40 PASS** | `…/pytest-verbose-combined.log` |
| Scenario harness, profile `current` | **18 / 18 PASS** | `…/evaluate-recommender-current.{log,json}` |
| Scenario harness, profile `client-ad` | **18 / 18 PASS** | `…/evaluate-recommender-client-ad.{log,json}` |

## 2. Reproduce verbatim

```bash
cd backend
python -m pytest tests/test_recommender.py -v          # 30 passed
python -m pytest tests/test_perf_v2.py -v              # 10 passed
python scripts/evaluate_recommender.py --profile current   --json out-current.json
python scripts/evaluate_recommender.py --profile client-ad --json out-client-ad.json
```

Note: the repo's `pyproject.toml` sets `addopts = "-q"`, so the per-test-name log was captured
with `-v -o addopts=''` (recorded verbatim at the top of `pytest-verbose-combined.log`).
Profile names are `current` and `client-ad` (there is no profile literally named "balanced";
`current` is the balanced 30/30/20/15/5 split).

## 3. Environment

Local sandbox — full spec in `…/t-2.3-acceptance/env.txt`: Python 3.11.2, pytest 9.1.1,
2 vCPU Intel Xeon @ 2.60 GHz, 3.8 GiB RAM, Debian 12. Both suites are **hermetic by design**
(SQLite + hash embeddings + fakeredis/`use_cache=False`): they measure ranking *logic* and
algorithmic latency bounds, not infrastructure. Infrastructure-level p95 evidence is T-2.2
(`docs/reports/perf_head.md`), per supervisor amendment A1.

**CI corroboration (A2):** the `backend` CI job executes these same suites inside its full
`pytest tests/` run on real service containers on every push of this branch; the job log
excerpt for this commit is attached in the same evidence dir once the run completes
(`ci-backend-corroboration.log`).

## 4. The 30 acceptance tests (all PASSED)

01 returns_results_for_default_quiz · 02 budget_hard_filter_respected · 03 low_budget_industrial ·
04 high_budget_scandinavian_large_room · 05 only_verified_products_recommended ·
06 impossible_budget_returns_empty · 07 results_capped_between_3_and_5 ·
08 results_sorted_by_final_score · 09 style_preference_ranks_matching_style_first ·
10 walnut_wood_material_preference · 11 minimal_style_white_palette ·
12 classic_persian_rug_pattern · 13 weights_sum_to_one · 14 budget_score_midpoint_is_one ·
15 budget_score_edges_are_zero · 16 color_distance_identical_is_zero ·
17 color_distance_black_white_is_high · 18 color_score_close_palettes_high · 19 jaccard_math ·
20 explanation_contains_all_components · 21 explanation_percentages_in_range ·
22 explanation_summary_format · 23 matched_materials_listed ·
24 calculate_score_final_is_weighted_sum · 25 cache_key_stable_and_order_independent ·
26 second_call_served_from_cache · 27 cache_has_ttl · 28 empty_optional_fields_do_not_crash ·
29 all_categories_covered_with_wide_budget · 30 p95_latency_under_2s

`test_perf_v2.py` adds: cache-key scoping ×6, single-flight ×3, HNSW `ef_search` floor ×1.

## 5. Scenario harness (18/18 under both profiles)

Per-scenario table with exact inputs in the two JSON artifacts. Both weight profiles produce
identical PASS sets; the C-6 client decision (which profile ships) remains **open with the
client** and is *not* blocked by this battery — both candidates satisfy every acceptance
scenario. Weight/version stamps verified in scenario 16
(`weights_version=2026-08-26.1`, `recommender=2026-08-26.1`).

## 6. SA-7 critique log

- *Sample size:* suites are deterministic (fixed seeds, hash embeddings); n=1 run is the
  correct methodology for logic assertions — latency-style claims (test 30) are bounded
  assertions re-verified in CI, and infrastructure p95 is measured separately in T-2.2.
- *No cherry-picking:* the scoped commands are the full files; the verbose log proves 0
  deselected/skipped within scope.
- *Failed-invocation note:* one wrong invocation (`--profile balanced`, exit 2) preceded the
  real runs and is disclosed here; corrected profile names recorded in §2.
