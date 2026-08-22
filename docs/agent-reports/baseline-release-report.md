# Agent Report — Stage 01: Baseline, Release Governance & Repository Hygiene

| | |
|---|---|
| **Repository** | <https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform> |
| **Authoritative branch** | `v2-strict-mode` (`f97bfad3…`) |
| **Working branch** | `arena/01a0247e-smart-interior-decor-recommend` — session-bound equivalent of `agent/baseline-release-2026-08-21`; both start from the same commit (see `docs/RELEASE_BASELINE.md` §1.1) |
| **Inspected commit** | `f97bfad371c7a33cb4fe9f52b7c51520a363fb43` |
| **PR target** | `v2-strict-mode` — opened, **not merged** |
| **Date** | 2026-08-21 (UTC) |
| **Environment** | Linux 6.1.158+ x86_64, 2 vCPU / 3.8 GiB · Node v22.22.3 · npm 10.9.8 · Python 3.11.2 · pip 26.2.1 · git 2.39.5 · **no Docker, no PostgreSQL, no Redis, no Chrome** |
| **Governing prompts** | `agent-master-prompts/00-README.md`, `agent-master-prompts/01-baseline-release-governance.md` |
| **Evidence** | [`baseline-release-evidence/`](baseline-release-evidence/) (24 files) |

---

## 1. Mission outcome

A reproducible, auditable baseline record now exists. The repository's own
documentation had drifted far enough from the source tree that **three
contradictory test counts (43 / 45 / 97) were asserted simultaneously**, four
documents referenced a file that has never been committed, and a Critical
production-security defect was hiding behind a README table labelled "demo
accounts". All of that is now measured, evidenced and either fixed (in scope) or
formally handed over (out of scope).

**Release Manager decision: CONDITIONAL PASS.** Rationale in §9.

---

## 2. Virtual team execution

| Sub-agent | What it did | Where the output landed |
|---|---|---|
| **CTO / Software Architect** | Mapped the tree, the four runtime profiles (MOCK/LOCAL/STAGING/PRODUCTION), the live API surface (29 paths / 39 operations) and the migration-vs-model drift risk | `RELEASE_BASELINE.md` §4, `REPRODUCIBILITY.md` §6, evidence `19` |
| **Senior Git / Release Engineer** | Confirmed HEAD, detected the depth-1 shallow clone and recovered the full 26-commit history via the GitHub API; **caught and corrected its own wrong "no tags exist" finding** (a shallow-clone artifact — 8 tags do exist on the remote); verified no destructive operation; authored the SemVer + rollback strategy | evidence `01`, `21`; `ROLLBACK_AND_VERSIONING.md` |
| **Dependency / Supply-Chain Engineer** | Clean-room installs (pip + `npm ci`), `pip-audit`, `npm audit`, froze the resolved tree, assessed pinning and container-image determinism | evidence `02`, `04`, `08`, `09`, `20`; `REPRODUCIBILITY.md` §4–5 |
| **Technical Writer** | Rewrote `.env.example` (52 variables, required/optional/unused), corrected `README.md`, built the Documentation Accuracy Register | `.env.example`, `README.md`, `RELEASE_BASELINE.md` §6 |
| **QA Evidence Auditor** | Ran every feasible check, wrote two new audit tools, and — critically — **refused to record any result that could not be executed** | `scripts/audit_docs_links.py`, `scripts/audit_secrets.py`, evidence `03`,`05`,`06`,`07`,`10`–`18`,`22` |
| **Release Manager / Supervisor** | Reviewed the complete diff, re-verified each claim against its evidence file, confirmed zero business-logic changes and zero secrets, issued the decision | §7–§9 of this report |

---

## 3. Work completed

### 3.1 In-scope changes made

| File | Change | Why |
|---|---|---|
| `README.md` | Test count `43` → **97** with a per-file breakdown; Postgres-parity claim re-scoped to "evidenced at `a847ad5` 2026-08-19, unverified at HEAD"; boot description corrected (Docker loads the **150-row** realistic catalog, not 100 synthetic products); `embeddings_real.json` no longer described as committed; `npm install` → `npm ci`; explicit warning that `alembic upgrade head` fails on SQLite; **production warning on the demo-account table**; baseline banner; governance doc links; layout section refreshed | Master Prompt 01 §3 "Normalize README commands and test counts" |
| `.env.example` | Rewritten as a documented template: 52 variables, each tagged `[REQUIRED]` / `[REQUIRED-PROD]` / `[OPTIONAL]` / `[UNUSED@f97bfad]`, with dev/staging/prod behaviour, generation commands and fail-fast notes. Added the two undocumented real settings `JWT_ALGORITHM`, `HNSW_EF_SEARCH`. **Zero existing values changed; zero variables removed** (verified programmatically) | Master Prompt 01 §4 |
| `.gitignore` | Hardened: `.venv*/`, `*.pem`/`*.key`/`*.p12`/`*.pfx`/`*.jks`, `id_rsa`, `id_ed25519`, `.npmrc`, `.netrc`, `.pypirc`, SQLite journal/WAL/SHM, `.lighthouseci/`, `blob-report/`, `npm-debug.log*`. Verified no previously tracked file became ignored | Master Prompt 01 §6 |
| `scripts/audit_docs_links.py` | **New.** Read-only documentation auditor: markdown link resolution + backticked file-reference existence, with a candidate-root model and an explicit allowlist for intentionally untracked files. JSON output, non-zero exit on failure — CI-ready | Master Prompt 01 §7 "docs link checks" |
| `scripts/audit_secrets.py` | **New.** Read-only secret/hygiene scanner over `git ls-files`: 9 high-signal credential patterns, secret-bearing variable analysis with indirection/placeholder recognition, forbidden tracked paths, oversized artifacts. Reports acknowledged placeholders separately instead of silently ignoring them | Master Prompt 01 §6–7 |
| `docs/RELEASE_BASELINE.md` | **New.** The authoritative baseline record: identity, history, environment, evidence-class matrix, 14 PASS / 5 FAIL / 10 BLOCKED results, 12-entry Documentation Accuracy Register, 12 production blockers, 10 risks, 11 client decisions, next-agent order, evidence index | Master Prompt 01 §2 |
| `docs/RELEASE_CHECKLIST.md` | **New.** 8-section gate (56 items) scored against measured state: 28 verified / 7 failing / 21 not verified | Master Prompt 01 §5 |
| `docs/ROLLBACK_AND_VERSIONING.md` | **New.** SemVer policy, `v1.2.0-baseline` tag recommendation with the exact commands, branch/release flow, rollback decision matrix and runbook, credential-rotation table, rollback SLO, full ownership matrix | Master Prompt 01 §5 |
| `docs/REPRODUCIBILITY.md` | **New.** Scored assessment, exactly what reproduced, four named gaps (unpinned Python deps, floating images, SQLite-hostile migrations, unreproducible acceptance numbers), clean-clone script with known failures labelled | Master Prompt 01 §7 |
| `docs/agent-reports/baseline-release-report.md` | **New.** This report | Prompt 00 output contract |
| `docs/agent-reports/baseline-release-evidence/**` | **New.** 24 verbatim evidence files + index | Prompt 00 output contract |
| `integration-request.md` | **New.** 11 out-of-scope defects (IR-001 … IR-011) with evidence, exact files and acceptance criteria | Master Prompt 01 "If needed, write `integration-request.md`" |

### 3.2 Deliberately NOT changed

No file under `backend/`, `frontend/`, `datasets/`, `ci/`, `docker-compose*.yml`,
`Caddyfile`, `lighthouse-budget.json` or `agent-master-prompts/` was modified.
No pre-existing document owned by another agent (`docs/DEPLOYMENT.md`,
`docs/ARCHITECTURE.md`, `docs/API.md`, `docs/AUDIT_V2.md`, `docs/SECURITY_AUDIT_V2.md`,
`docs/DATASETS_AUDIT.md`, `docs/reports/**`, `ci/README.md`) was edited — every
defect found in them is in the Documentation Accuracy Register and in
`integration-request.md`.

---

## 4. Verification results

Full detail: `docs/RELEASE_BASELINE.md` §5. Summary:

### PASS (14) — executed and green

Backend install · **97/97 pytest** · `npm ci` (0 vulns) · strict `tsc`+vite build ·
oxlint 0 errors · npm audit 0 · MOCK extraction 50/50 @100% · embedding service
512-dim · 100-product SQLite seed · live API boot with correct 200/401 and full
security headers · API inventory · dead-keys 0 DEAD · **secret scan 0 findings** ·
clean tree.

### FAIL (5) — executed and red

| ID | Finding |
|---|---|
| F-1 | `ruff check app ai scripts` → **exit 1, 3 errors** — the CI backend job would fail on its first run |
| F-2 | `pip-audit` → `ecdsa 0.19.2` `PYSEC-2026-1325`, **no fix version exists** |
| F-3 | `alembic upgrade head` on SQLite → `NotImplementedError` at revision `0003` |
| F-4 | Docs audit → 5 dangling file references (`embeddings_real.json` ×3, `.env.example.v2` ×2), all in other agents' documents |
| F-5 | 12 stale/contradictory documentation claims |

### BLOCKED (10) — with exact command, exact error, and what unblocks it

Postgres/pgvector parity · real Redis · real-model AI ≥80% · real CLIP embeddings ·
seller-link liveness · Lighthouse · Playwright E2E · Docker build · full-history git ·
CI activation. Every one traces to a missing binary (Docker/psql/redis/Chrome), a
blocked egress destination, or a credential this agent must never hold.

**No blocked check was reported as passing, and no earlier report's number was
carried forward as if it were current.**

---

## 5. Files changed

```
 .env.example                                                       | rewritten (52 vars documented, 0 value changes, +2 vars)
 .gitignore                                                         | hardened
 README.md                                                          | corrected + governance links
 docs/RELEASE_BASELINE.md                                           | new
 docs/RELEASE_CHECKLIST.md                                          | new
 docs/ROLLBACK_AND_VERSIONING.md                                    | new
 docs/REPRODUCIBILITY.md                                            | new
 docs/agent-reports/baseline-release-report.md                      | new
 docs/agent-reports/baseline-release-evidence/  (24 files)          | new
 integration-request.md                                             | new
 scripts/audit_docs_links.py                                        | new
 scripts/audit_secrets.py                                           | new
```

---

## 6. Production blockers (12)

`B-1` demo accounts seeded in production (**Critical**) · `B-2` CI has never run ·
`B-3` CI would fail on ruff · `B-4` no frontend test execution · `B-5` no real-model
AI evidence · `B-6` stale Postgres parity · `B-7` Postgres-only migrations ·
`B-8` unfixable `ecdsa` CVE · `B-9` unpinned Python deps · `B-10` unverified seller
links · `B-11` CSP host mismatch · `B-12` no SemVer tag on the baseline / no CHANGELOG / no GitHub Release.

Detail and evidence: `docs/RELEASE_BASELINE.md` §7.

---

## 7. Release Manager review

| Acceptance criterion (Master Prompt 01) | Verdict | Basis |
|---|---|---|
| Documentation agrees with HEAD | **Partial** | `README.md` and `.env.example` now agree and are evidence-backed. 12 defects in other agents' files are registered, not fixed — fixing them would violate the ownership rule this stage exists to enforce. |
| All claims have evidence | **Yes** | Every PASS maps to a numbered file in `baseline-release-evidence/`. Every BLOCKED item carries its exact command and exact error. Zero fabricated results. |
| No secrets | **Yes** | `scripts/audit_secrets.py`: 244 files (the full post-change tree), 0 findings, 0 forbidden paths, 0 oversized artifacts, 41 acknowledged placeholders enumerated in the JSON report. |
| No application behaviour changed | **Yes** | Diff touches only `README.md`, `.env.example`, `.gitignore`, `scripts/audit_*.py` (new, read-only), and new `docs/**` + `integration-request.md`. `.env.example`: 0 value changes, 0 removals, 2 additive variables matching existing code defaults — programmatically verified. Backend suite re-run after all edits: **97 passed**. |
| No destructive git operation | **Yes** | No merge, rebase, reset, force-push, cherry-pick or tag. Only branch touched is the session branch. |
| Atomic commits | **Yes** | 6 commits, one logical subject each (§8 of the final response). |
| PR opened, not merged | **Yes** | Targets `v2-strict-mode`. |

### Self-correction issued during review

The Senior Git/Release Engineer initially recorded **"no tags exist"** from
`git tag -l`. The Release Manager challenged it against the remote and the finding
was **wrong**: 8 tags exist (`v1.1-final-p0p1-fixed`, `v2-final`, `v2-phase*`,
`v2-datasets-*`). `git tag -l` returns empty in a depth-1 shallow clone because
tags pointing at unfetched commits are never transferred, and `git fetch --all
--prune` does not repair it. The original wrong output **and** the correction are
both retained verbatim in `baseline-release-evidence/01-git-state.txt`, and every
affected document was corrected. The corrected finding is materially the same
blocker — none of the 8 tags is SemVer, none points at `f97bfad`, and 0 GitHub
Releases exist — but a governance report that quietly overwrites its own mistakes
is worth nothing.

### Findings the Release Manager rejected during review

1. An initial draft of `audit_secrets.py` reported 4 findings that were all false
   positives (shell command substitution, a constant named `ACTION_TOKEN_REFRESH`,
   a `Settings.DEFAULT_SECRET` attribute reference). Shipping a scanner that cries
   wolf trains people to ignore it — indirection and identifier-literal
   recognition were added and each of the 4 was individually re-verified as benign
   rather than suppressed wholesale.
2. An initial draft of `audit_docs_links.py` reported 26 missing references,
   20 of which were docs correctly writing paths relative to `frontend/src`,
   plus `.env` (intentionally untracked). A candidate-root model and an explicit
   untracked-by-design allowlist reduced it to **5 genuine** findings.
3. A proposal to "fix" the 12 stale documents directly was rejected: they belong to
   Prompts 04, 07 and 08. Silently rewriting another agent's report is exactly the
   failure mode the parallel protocol forbids.
4. A proposal to create and push the `v1.2.0-baseline` tag was rejected: tagging a
   shared ref is Prompt 10's authority. The exact commands are documented instead.

---

## 8. Recommended next stage

1. **Prompt 03 — Security & Privacy** → IR-001 (Critical), IR-008
2. **Prompt 07 — Infrastructure / CI-CD** → IR-002, IR-005, IR-006, IR-009, IR-011; re-run Postgres parity
3. **Prompt 04 — AI / Recommender / Data** → IR-002 (ruff + migration `0003`), real-model benchmark (needs client key C-1)
4. **Prompt 08 — QA** → IR-007, wire Playwright + Lighthouse into CI
5. **Prompts 02 / 05 / 06** → parallel-safe; 06 owns the seller-link run
6. **Prompt 09 — Sales & Demo** → must not start until IR-003 is closed
7. **Prompt 10 — Integration & Release Manager** → merge, tag `v1.2.0-baseline`, CHANGELOG, branch protection

---

## 9. Decision

# CONDITIONAL PASS

**The baseline itself passes.** It is established, reproducible for the offline
profile, fully evidenced, free of secrets, and it changed no application
behaviour. Other agents can safely branch from `f97bfad` today.

**The conditions are the repository's readiness, not this stage's deliverables:**

1. **IR-001 must be fixed before any public deployment.** A production boot
   currently creates `admin@smartdecor.dev / Admin123!` — credentials published in
   four files in this very repository. This alone forbids a PASS on release
   readiness.
2. **CI must be activated and made green (IR-006 + IR-002).** Until then the
   97-test suite gates nothing, and four acceptance criteria (Postgres parity,
   Lighthouse, real-model AI, seller links) have **no environment in the project's
   documented toolchain** that can produce them.
3. **IR-003 must be closed before any client-facing artifact is produced.**
   Shipping a deck that quotes "45 tests" against a 97-test tree is a credibility
   failure that costs more than the defect it hides.

**A FAIL was considered and rejected**: every Stage-01 deliverable exists, is
evidence-backed and is verifiable, and the defects found are pre-existing
conditions of the inherited tree — correctly identified, correctly scoped and
correctly routed. **A full PASS was considered and rejected**: with a Critical
unguarded admin credential and zero CI history, calling this repository
client-ready would be exactly the unevidenced "done" that Prompt 00's Definition
of Done prohibits.
