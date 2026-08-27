# Stage 2 report — Performance, Evidence & CI Consolidation (close-out)

**Date:** 2026-08-27 (UTC) · **Branch:** `arena/01a04481-smart-interior-decor-recommend` (platform-locked name, deviation D-0)
**Base:** `main` = `ad4d895c` (merge of PR #15, series tip `65f4783`) · **Stage-1 tag:** `v0.5.0` = `e948b802`
**Scope of this document:** the Stage-2 close-out sections — gate table, performance journey,
deviations ledger, the T-2.6 consolidation ruling, and the §H-3 human hand-off. Task-level
detail lives in the per-task evidence: `docs/reports/recommender_acceptance.md` (T-2.3),
`docs/reports/perf_head.md` (T-2.2 iteration), `docs/reports/ACCEPTANCE_EVIDENCE.md`
(client-facing matrix), `docs/reports/seller_links.md` (T-2.5),
`docs/agent-reports/stage2-evidence/` (raw logs).

All CI numbers below were read from the public GitHub API (runs, job logs, check-run
annotations, artifact listings) — zero fabrication; where a number comes from the
supervisor-verified ledger rather than a fetch performed while writing this document, it is
marked *(ledger)*.

---

## 1. Gate table (state of record: run 33102053859 on `main`/`ad4d895c`)

| Job | Blocking? | Conclusion | Note |
|---|---|---|---|
| Backend — pytest vs Postgres16+pgvector & Redis | yes | **success** | includes T-2.3 suites + T-2.4 CSP anti-drift test |
| Multi-worker shared-Redis verification | yes | **success** | |
| Frontend — install, lint, typecheck, test, build | yes | **success** | |
| E2E — Playwright (auth negatives + three-role journeys) | yes | **success** | dead-key sweep step stays advisory (IR-S1-013, Stage 3) |
| Security & docs gates | yes | **success** | |
| Docker — compose config and image builds | yes | **success** | |
| p95 evidence — /recommend (T-2.2) | yes | **success** | cold p95 1616.8 ms / warm 154.3 ms at `65f4783`, 250/cell, 0 errors |
| Seller-link liveness (T-2.5) | advisory (A4) | **success** | 12/20 valid — honest classification in `docs/reports/seller_links.md` |
| Lighthouse CI — performance and accessibility | waived (IR-S1-010, until this PR) | **failure** | old anonymous treosh layer only — see §3; the matrix never got to run |

The overall run concluded **success** only because the Stage-1 `continue-on-error` waiver was
still active. This PR (T-2.6a) removes the waiver — after the §H-3 paste the job is blocking,
and with T-2.6b its one flaky layer no longer asserts.

Contract-evidence runs at the frozen perf commit `65f4783`: **33086824717** (push) and
**33086828679** (pull_request) — every job green **including** lighthouse, matrix
"All asserted gates passed" in both, 12/12 cells, a11y 96–100, secret scan 0 hits.

## 2. Performance journey (T-2.1 — supervisor-verified; PERF IS FROZEN)

Measured page: `/recommendations` (authenticated), mobile form factor, CI matrix.

| Commit | LCP (ms) | What changed |
|---|---|---|
| `c1e02d5` | 6556 | Stage-2 baseline *(ledger)* |
| `1dda1c5` | 5989 | first pass *(ledger)* |
| `52c3224` | 6564 | re-baseline; LCP phases TTFB 453 / Load Delay 5145 / Load Time 255 / Render Delay 711 *(ledger)* |
| `ad6b6a7` | — | image path solved — LCP load delay down to 726 ms *(ledger)* |
| `28686e0` | 6497 | image no longer the bottleneck; CPU is *(ledger)* |
| `8d837b1` + `65f4783` | **2338** | first-viewport commit before LCP broke the CPU bottleneck — verified in both runs above |

Final state at `65f4783` (both runs): perf **98/97**, LCP **2338/2338**, TTI **2361**,
CLS **0.010**, TBT **78–94 ms**; LCP phases TTFB 452 / Load Delay 746–775 / Load Time
108–111 / Render Delay 1004–1030. All 12 matrix cells pass; home TTI 1289 ms in both runs
(~1285 ± 10 across ≥ 4 runs, *(ledger)*). **No further optimization commits are permitted.**

## 3. T-2.6 — the treosh consolidation ruling (documented, not silently dropped)

**Finding (supervisor, 2026-08-27):** `main` run **33102053859** failed the lighthouse job on
the **old anonymous treosh layer**: one assertion, `interactive` (TTI) **4274.4527 ms** vs the
4000 ms budget on `http://127.0.0.1:4173/` (check-run annotation, verbatim). The failure
killed the job **before the authenticated matrix ran** — proven by the artifact-upload warning
“No files were found with the provided path: /tmp/lighthouse-matrix/” and the `skipped`
matrix steps. The matrix measures the same page at ~1285 ms ± 10 TTI across ≥ 4 runs: the
anonymous single-shot number is a knife-edge scheduling flake with 4× worse stability than
the layer that already enforces the same thresholds.

**Ruling:** the authenticated matrix is THE gate (`perf ≥ 80`, `LCP < 3000`, `TTI ≤ 4000` on
home, plus the contract gates on `/recommendations`). The anonymous layer keeps running and
keeps uploading its report (`uploadArtifacts: true`) but no longer asserts
(`budgetPath` removed). `lighthouse-budget.json` is unchanged — no budget was relaxed; a
duplicate, flakier assertion point was consolidated into the stronger one.

Changes land in `ci/ci.stage2.yml` only (standing rule — the agent token cannot push
`.github/workflows/*`):

| Commit | Change |
|---|---|
| `ci(T-2.6a)` | remove `continue-on-error: true` from the lighthouse job → restores IR-S1-010 as blocking |
| `ci(T-2.6b)` | remove `budgetPath` from the treosh step (keep `uploadArtifacts`), with the ruling + 4274-vs-1285 evidence cited in a comment |
| `ci(T-2.6c)` ×4 | action bumps, one per commit, each tag verified upstream first: `actions/checkout@v5` (fbc6f39), `actions/setup-node@v5` (a0853c2), `actions/setup-python@v6` (ece7cb0), `actions/upload-artifact@v5` (330a01c) — also clears the runner’s “Node.js 20 deprecated” warnings |

**T-2.6d note:** the e2e job’s envs, run blocks and blocking/advisory sweep split are
byte-identical to `main` (machine-verified by YAML comparison). The only lines that changed
inside the e2e job are the four `uses:` version strings, which is the explicit T-2.6c
instruction applied file-wide; flagged here so the supervisor can review that interpretation.

## 4. Deviations ledger

| ID | Deviation | Status |
|---|---|---|
| **D-0** | Branch names are platform-locked (`arena/…` instead of the prompt’s `agent/…` scheme); workflow files travel via `ci/ci.stage2.yml` because the agent token is refused on `.github/workflows/*` (IR-S1-009) | standing, unchanged |
| **D-1** | PR #15 (the T-2.1 optimization series) was merged by the human **before** supervisor review | stood; post-hoc supervisor review passed — recorded, no rework |
| **D-2 (this PR)** | The anonymous treosh budget assertion is consolidated into the authenticated matrix (T-2.6b) — a *reduction of a redundant assertion point*, done by explicit supervisor ruling with the evidence in §3 | documented here, in the workflow comment, and in `ACCEPTANCE_EVIDENCE.md` §2 |

IR ledger: **IR-S1-010 is CLOSED** by this PR (entry updated in `integration-request.md`
with the restore-condition math); IR-S1-011/012/013 remain open and assigned to Stage 3.

## 5. §H-3 — Human hand-off: activate the close-out workflow

The staged workflow is ahead of the active one by **§H-2** (the three
`--expand-to 150` seed lines, staged on `main` before this PR) **plus** the T-2.6 edits from
this PR. One paste applies all of it:

```bash
cp ci/ci.stage2.yml .github/workflows/ci.yml
git add .github/workflows/ci.yml
git commit -m "ci: activate the Stage-2 close-out workflow (T-2.6, §H-2+§H-3)"
git push
```

Paste **only after supervisor approval of this PR**. After the paste, T5 requires the
lighthouse job to be **blocking and green in ≥ 2 consecutive runs at the final HEAD** (the
push + PR events provide these naturally) before Stage 2 is declared closed. Merge decision,
tagging (v0.6.0) and Stage 3 are supervisor/human actions — not the agent’s.

### Full staged-vs-active diff (verbatim; what the paste will change)

```diff
--- .github/workflows/ci.yml   (ACTIVE, main @ ad4d895c)
+++ ci/ci.stage2.yml           (STAGED, this PR HEAD)
@@ -56,10 +56,10 @@
 
     steps:
       - name: Checkout
-        uses: actions/checkout@v4
+        uses: actions/checkout@v5
 
       - name: Set up Python
-        uses: actions/setup-python@v5
+        uses: actions/setup-python@v6
         with:
           python-version: "3.12"
           cache: pip
@@ -85,7 +85,7 @@
 
       - name: Upload locked-install proof
         if: always()
-        uses: actions/upload-artifact@v4
+        uses: actions/upload-artifact@v5
         with:
           name: backend-lock-verification
           path: |
@@ -179,7 +179,7 @@
 
       - name: Upload dependency audit report
         if: always()
-        uses: actions/upload-artifact@v4
+        uses: actions/upload-artifact@v5
         with:
           name: backend-dependency-audit
           path: |
@@ -261,10 +261,10 @@
 
     steps:
       - name: Checkout
-        uses: actions/checkout@v4
+        uses: actions/checkout@v5
 
       - name: Set up Python
-        uses: actions/setup-python@v5
+        uses: actions/setup-python@v6
         with:
           python-version: "3.12"
           cache: pip
@@ -294,10 +294,10 @@
 
     steps:
       - name: Checkout
-        uses: actions/checkout@v4
+        uses: actions/checkout@v5
 
       - name: Set up Node.js
-        uses: actions/setup-node@v4
+        uses: actions/setup-node@v5
         with:
           node-version: "22"
           cache: npm
@@ -351,7 +351,7 @@
           test "$HITS" -eq 0
 
       - name: Upload frontend artifact
-        uses: actions/upload-artifact@v4
+        uses: actions/upload-artifact@v5
         with:
           name: frontend-dist
           path: frontend/dist
@@ -418,10 +418,10 @@
 
     steps:
       - name: Checkout
-        uses: actions/checkout@v4
+        uses: actions/checkout@v5
 
       - name: Set up Python
-        uses: actions/setup-python@v5
+        uses: actions/setup-python@v6
         with:
           python-version: "3.12"
           cache: pip
@@ -449,7 +449,7 @@
           python scripts/seed_products.py
 
       - name: Set up Node.js
-        uses: actions/setup-node@v4
+        uses: actions/setup-node@v5
         with:
           node-version: "22"
           cache: npm
@@ -521,7 +521,7 @@
       # not only when something breaks.
       - name: Upload e2e report (JSON + HTML) and traces
         if: always()
-        uses: actions/upload-artifact@v4
+        uses: actions/upload-artifact@v5
         with:
           name: e2e-report
           path: frontend/test-results
@@ -532,15 +532,15 @@
 
     steps:
       - name: Checkout
-        uses: actions/checkout@v4
+        uses: actions/checkout@v5
 
       - name: Set up Python
-        uses: actions/setup-python@v5
+        uses: actions/setup-python@v6
         with:
           python-version: "3.12"
 
       - name: Set up Node.js
-        uses: actions/setup-node@v4
+        uses: actions/setup-node@v5
         with:
           node-version: "22"
 
@@ -567,7 +567,7 @@
 
     steps:
       - name: Checkout
-        uses: actions/checkout@v4
+        uses: actions/checkout@v5
 
       - name: Provide placeholder environment
         run: |
@@ -611,26 +611,28 @@
   lighthouse:
     name: Lighthouse CI — performance and accessibility
     runs-on: ubuntu-latest
-    # WAIVED FOR STAGE 1 (IR-S1-010). The perf budget currently fails on TTI
-    # (interactive 6727ms vs a 4000ms budget); performance tuning is Stage 2
-    # scope, so this job reports but does not block. Stage-2 task G-2.6
-    # removes this line and restores it as a required check.
-    continue-on-error: true
+    # RESTORED AS BLOCKING (Stage 2, T-2.6 — closes IR-S1-010). The Stage-1
+    # waiver (`continue-on-error: true`) is removed: the IR-S1-010 restore
+    # conditions are met on the authenticated matrix, which enforces
+    # perf >= 80 / LCP < 3000 ms / TTI <= 4000 ms on home plus the contract
+    # gates on /recommendations (measured on 65f4783: home perf=100,
+    # LCP 1281–1282 ms, TTI 1289 ms; recommendations/mobile perf 98/97,
+    # LCP 2338 ms — runs 33086824717 and 33086828679).
     needs:
       - frontend
       - backend
 
     steps:
       - name: Checkout
-        uses: actions/checkout@v4
+        uses: actions/checkout@v5
 
       - name: Set up Node.js
-        uses: actions/setup-node@v4
+        uses: actions/setup-node@v5
         with:
           node-version: "22"
 
       - name: Set up Python
-        uses: actions/setup-python@v5
+        uses: actions/setup-python@v6
         with:
           python-version: "3.12"
 
@@ -656,7 +658,7 @@
           # Stage 2 (T-2.1/A3): seed the REAL 150-product catalog (images,
           # retailer links) instead of the tiny demo set, so the measured
           # /recommendations page renders representative content.
-          python scripts/load_realistic_products.py --realistic --if-empty
+          python scripts/load_realistic_products.py --realistic --if-empty --expand-to 150
 
       - name: Start backend
         working-directory: backend
@@ -782,12 +784,23 @@
         with:
           # Stage 2 (A3): the anonymous /recommendations URL was removed — it
           # measured the RequireAuth login redirect, not the page (wrong-page
-          # artifact behind the IR-S1-010 numbers). The budget is asserted on
-          # the public home page; /recommendations is measured AUTHENTICATED
-          # by the matrix step below.
+          # artifact behind the IR-S1-010 numbers). /recommendations is
+          # measured AUTHENTICATED by the matrix step below.
+          #
+          # Stage 2 (T-2.6b, supervisor ruling 2026-08-27): budgetPath removed —
+          # this anonymous layer now REPORTS ONLY (uploadArtifacts kept). It
+          # duplicated the home-page assertions the authenticated matrix
+          # already enforces (perf >= 80 / LCP < 3000 / TTI <= 4000 on home,
+          # plus the contract gates on /recommendations), with far worse
+          # stability: main run 33102053859 failed HERE on a knife-edge
+          # single-shot TTI of 4274 ms vs the 4000 ms budget — and killed the
+          # job before the matrix ran — while the matrix measures the same
+          # page at ~1285 ms (±10) TTI across >= 4 runs. Consolidated, not
+          # silently dropped: docs/agent-reports/stage2-report.md §T-2.6 and
+          # docs/reports/ACCEPTANCE_EVIDENCE.md carry the full ruling. The
+          # budget file (lighthouse-budget.json) itself is unchanged.
           urls: |
             http://127.0.0.1:4173/
-          budgetPath: ./lighthouse-budget.json
           uploadArtifacts: true
           temporaryPublicStorage: false
 
@@ -860,7 +873,7 @@
 
       - name: Upload Lighthouse matrix (JSON + HTML, all cells)
         if: always()
-        uses: actions/upload-artifact@v4
+        uses: actions/upload-artifact@v5
         with:
           name: lighthouse-matrix
           path: /tmp/lighthouse-matrix/
@@ -921,10 +934,10 @@
 
     steps:
       - name: Checkout
-        uses: actions/checkout@v4
+        uses: actions/checkout@v5
 
       - name: Set up Python
-        uses: actions/setup-python@v5
+        uses: actions/setup-python@v6
         with:
           python-version: "3.12"
 
@@ -939,7 +952,7 @@
         working-directory: backend
         run: |
           alembic upgrade head
-          python scripts/load_realistic_products.py --realistic --if-empty
+          python scripts/load_realistic_products.py --realistic --if-empty --expand-to 150
           python scripts/seed_perf_products.py
           # MANDATORY (T-2.2 finding): without fresh statistics the planner
           # estimated 564 rows in the 20 150-row table and chose a Seq Scan
@@ -1020,7 +1033,7 @@
 
       - name: Upload p95 evidence artifacts
         if: always()
-        uses: actions/upload-artifact@v4
+        uses: actions/upload-artifact@v5
         with:
           name: p95-evidence
           path: /tmp/p95-evidence/
@@ -1053,10 +1066,10 @@
 
     steps:
       - name: Checkout
-        uses: actions/checkout@v4
+        uses: actions/checkout@v5
 
       - name: Set up Python
-        uses: actions/setup-python@v5
+        uses: actions/setup-python@v6
         with:
           python-version: "3.12"
 
@@ -1070,7 +1083,7 @@
         working-directory: backend
         run: |
           alembic upgrade head
-          python scripts/load_realistic_products.py --realistic --if-empty
+          python scripts/load_realistic_products.py --realistic --if-empty --expand-to 150
 
       - name: "Check every seller link — polite 1 req/s, retry network errors"
         run: |
@@ -1083,7 +1096,7 @@
 
       - name: Upload link-liveness artifacts
         if: always()
-        uses: actions/upload-artifact@v4
+        uses: actions/upload-artifact@v5
         with:
           name: link-liveness
           path: /tmp/link-liveness/
```

*End of §H-3. 27 of the changed lines are the four action bumps; 3 are §H-2 (`--expand-to
150`); the remainder is the T-2.6a waiver removal and the T-2.6b report-only treosh step
(comments included).*

## 6. Evidence index

| Topic | File / API object |
|---|---|
| Client-facing acceptance matrix | `docs/reports/ACCEPTANCE_EVIDENCE.md` |
| Recommender battery 30/30 + 10/10 + 18/18×2 | `docs/reports/recommender_acceptance.md`, `stage2-evidence/t-2.3-acceptance/` |
| p95 CI evidence | run 33086824717 job 98569566684, artifact `p95-evidence`; `docs/reports/perf_head.md` |
| Lighthouse matrix ×2 | runs 33086824717 / 33086828679, artifact `lighthouse-matrix` (26 files each) |
| Treosh flake evidence | run 33102053859, check-run 98622884610 annotations |
| Seller links | `docs/reports/seller_links.md`, artifact `link-liveness` (runs 33086824717, 33102053859) |
| CSP / B-11 closure | `stage2-evidence/t-2.4-csp/`, `backend/tests/test_csp_alignment.py`, `backend/scripts/print_csp.py` |
| IR-S1-010 closure | `integration-request.md` §IR-S1-010 |
