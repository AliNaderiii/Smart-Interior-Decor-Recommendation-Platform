# Acceptance Evidence — Stage 2 close-out (client-facing matrix)

**Date:** 2026-08-27 (UTC)
**Repository state of record:** `main` = `ad4d895c` (merge of PR #15; series tip `65f4783`)
**Prepared by:** Stage-2 close-out agent · **Reviewed against:** supervisor-verified ledger, 2026-08-27

Every number in this document is read from a GitHub Actions run, job log, annotation, or
uploaded artifact of this repository — run IDs and artifact names are given per row so each
figure can be re-derived from the public API. Nothing here is estimated or extrapolated.

---

## 1. Contract criteria → evidence → verdict

| # | Contract criterion | Measured result | Evidence (run / job / artifact) | Verdict |
|---|---|---|---|---|
| 1 | Lighthouse **performance ≥ 80** on the SPA | **97–100** on all 12 matrix cells (6 pages × mobile/desktop), twice | Runs **33086824717** (push) + **33086828679** (PR), commit `65f4783`, job *Lighthouse CI*, step *Authenticated Lighthouse matrix*; artifact `lighthouse-matrix` (26 files/run) | **PASS ×2** |
| 2 | **LCP < 3000 ms** (client acceptance metric) | Worst cell **2338 ms** (`/recommendations`, mobile, both runs); home 1281–1282 ms mobile, 285–287 ms desktop | same as #1 — per-cell JSON lines + summary table in the job log | **PASS ×2** |
| 3 | **TTI ≤ 4000 ms** budget (home) | **1289 ms** home/mobile in both runs (287/285 ms desktop); worst cell anywhere 2361 ms | same as #1 | **PASS ×2** |
| 4 | Accessibility (Lighthouse a11y) | **96–100** per cell (96 on home/login/recommendations, 100 on quiz/moodboards/shopping-list) | run 33086824717, per-cell JSON lines in the matrix step log | **PASS** |
| 5 | `/recommend` API **p95 < 2 s** (real Postgres 16 + pgvector + Redis) | Cold cell **p95 = 1616.8 ms**, warm cell **p95 = 154.3 ms** — 250 samples/cell, concurrency 20, **0 errors in 500 requests** | Run **33086824717**, job *p95 evidence* (`98569566684`); artifact `p95-evidence` (`load-recommend-ci.json`, `ef-search-sweep.*`, `bench-pgvector.*`, `environment.txt`); job green again on run **33102053859** | **PASS** (blocking CI gate) |
| 6 | Recommender acceptance battery (contract wording: “28 of 30”) | **30/30** acceptance + **10/10** perf-regression + **18/18** scenario checks under **both** weight profiles (`current`, `client-ad`) | `docs/reports/recommender_acceptance.md` + `docs/agent-reports/stage2-evidence/t-2.3-acceptance/` (verbatim pytest + harness logs); corroborated by the `backend` CI job on every push | **PASS** (exceeds contract) |
| 7 | Seller links live & classified | **20 links checked: 3 ok, 9 redirect, 5 dead, 3 unsafe → 12/20 valid**; dead/unsafe itemized per URL; unsafe hosts are refused (never fetched) | Run **33086824717**, job *Seller-link liveness* (`98569566672`); artifact `link-liveness`; full verdict in `docs/reports/seller_links.md` | **CLASSIFIED, honest** (advisory job — see §3) |
| 8 | CSP single source of truth (B-11) | `build_csp()` is the only definition; `backend/scripts/print_csp.py` generates the Caddyfile string; `backend/tests/test_csp_alignment.py` fails CI on any drift | `docs/agent-reports/stage2-evidence/t-2.4-csp/` (self-test log + header dump); tests run in the blocking `backend` job | **CLOSED** |
| 9 | CI green on the state of record | Run **33102053859** on `main`/`ad4d895c`: backend, multi-worker, frontend, e2e, security-scans, docker, p95-evidence all **success** | public API, run 33102053859 | **PASS** (see §2 for the one non-blocking failure) |

## 2. The one red job on `main` — and the ruling that resolves it

Run **33102053859** (`main` = `ad4d895c`): job *Lighthouse CI — performance and accessibility*
concluded **failure** on its **old anonymous single-shot layer** (treosh
`lighthouse-ci-action` asserting `lighthouse-budget.json`), with exactly one failed assertion
(job annotation, verbatim):

> `interactive` failure for `maxNumericValue` assertion — Expected <= 4000, but found **4274.4527** (`http://127.0.0.1:4173/`)

The step failure killed the job **before the authenticated matrix ran** (annotation: *“No
files were found with the provided path: /tmp/lighthouse-matrix/”* — the matrix steps show
`skipped`). The authenticated matrix measures the **same page** at TTI ≈ **1285 ms (±10)**
across ≥ 4 runs (supervisor-verified; 1289/1289 ms in the two runs tabled above). The
single-shot anonymous number is a knife-edge scheduling flake, not a regression.

**Supervisor ruling (2026-08-27):** the authenticated matrix is THE performance gate. The
redundant anonymous assertion is consolidated away in T-2.6(b) — `budgetPath` removed,
`uploadArtifacts` kept, so the anonymous layer still reports. This is documented here and in
`docs/agent-reports/stage2-report.md`; it is **not** a silent drop, and `lighthouse-budget.json`
itself is unchanged. With T-2.6(a) the lighthouse job simultaneously returns to **blocking**
(IR-S1-010 restore conditions met — see the closed ledger entry in `integration-request.md`).

## 3. Advisory jobs, stated honestly

- **Seller-link liveness** is advisory by design (supervisor amendment A4): third-party shop
  availability must not gate unrelated commits. The job has concluded **success** on every
  run to date; the honest classification (including 5 dead and 3 unsafe links) is in
  `docs/reports/seller_links.md`.
- The Playwright **dead-key sweep** remains advisory per IR-S1-013 (Stage-3 scope).

## 4. Performance journey (supervisor-verified ledger)

| Commit | Home/recommendations LCP (mobile, CI) | Note |
|---|---|---|
| `c1e02d5` | 6556 ms | Stage-2 baseline |
| `1dda1c5` | 5989 ms | first optimization pass |
| `52c3224` | 6564 ms | re-baseline; phases TTFB 453 / Load Delay 5145 / Load Time 255 / Render Delay 711 |
| `ad6b6a7` | — | image path solved (LCP load delay → 726 ms) |
| `28686e0` | 6497 ms | CPU bottleneck exposed |
| `8d837b1` + `65f4783` | **2338 ms** | first-viewport commit before LCP broke the CPU bottleneck — final, frozen |

Corroborating detail at `65f4783` (matrix job logs, both runs): LCP element phases
TTFB 452 / Load Delay 746–775 / Load Time 108–111 / Render Delay 1004–1030 ms; TBT 78–94 ms;
in-page `/recommend` fetch 30–31 ms (mobile) / 9–12 ms (desktop). **Performance is frozen** —
no further optimization commits are in scope.

## 5. Reproduction pointers

```text
gh api repos/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform/actions/runs/33086824717/jobs
gh api repos/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform/actions/runs/33086828679/jobs
gh api repos/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform/actions/runs/33102053859/jobs
gh api repos/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform/check-runs/98622884610/annotations
```

Artifacts per run: `lighthouse-matrix`, `lighthouse-results`, `p95-evidence`, `link-liveness`,
`e2e-report`, `backend-lock-verification`, `backend-dependency-audit`, `frontend-dist`.
