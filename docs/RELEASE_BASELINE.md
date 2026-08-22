# Release Baseline — Smart Interior Decor Recommendation Platform

> **Status of this document.** It is the single authoritative record of what is
> and is not true about this repository at the baseline commit. Every "PASS" in
> here is backed by a command and a captured output file. Anything that could
> not be executed is recorded as **BLOCKED** with the exact command, the exact
> error and the environment required to unblock it. Nothing in this document is
> inferred, extrapolated or copied forward from an earlier report.

---

## 1. Identity

| Field | Value |
|---|---|
| Repository | <https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform> |
| Authoritative branch | `v2-strict-mode` |
| Baseline commit (inspected) | `f97bfad371c7a33cb4fe9f52b7c51520a363fb43` (`f97bfad`) |
| Baseline commit subject | `Merge pull request #4 from AliNaderiii/chore/add-agent-master-prompts` |
| Baseline commit author / date | Ali Naderi — 2026-08-21T13:19:35Z |
| `v2-strict-mode` HEAD at audit time | `f97bfad3…` (identical to the inspected tree) |
| `main` HEAD at audit time | `0998ba4b…` (behind `v2-strict-mode` by 7 commits) |
| Working branch for this stage | `arena/01a0247e-smart-interior-decor-recommend` — see §1.1 |
| PR target | `v2-strict-mode` (not merged by this agent) |
| Audit date | 2026-08-21 (UTC) |
| Governing prompts | `agent-master-prompts/00-README.md`, `agent-master-prompts/01-baseline-release-governance.md` |
| Existing git tags | **8**, none SemVer-compliant and none on the baseline commit: `v1.1-final-p0p1-fixed` (`a847ad5`), `v2-phase0-audit-complete`, `v2-phase2-performance`, `v2-phase3-ui`, `v2-phase4-deadkeys`, `v2-final` (`dd2c34d`), `v2-datasets-realistic`, `v2-datasets-realistic-merged` (`939e05c`). **0 GitHub Releases.** See §2.1 |

### 1.1 Branch-name deviation (must be read)

Master Prompt 01 specifies the branch pattern `agent/baseline-release-<date>`,
and `agent/baseline-release-2026-08-21` **does exist on the remote** at
`f97bfad3…`. This session's execution environment is, however, hard-bound to the
session branch `arena/01a0247e-smart-interior-decor-recommend`; work committed to
any other branch is not associated with the session and would be lost.

Because both branches point at the same baseline commit `f97bfad`, the resulting
tree is byte-identical to what would have been produced on
`agent/baseline-release-2026-08-21`. The integration manager (Prompt 10) can
fast-forward or cherry-pick this branch onto `agent/baseline-release-2026-08-21`
with no conflict. **No other branch was created, modified, merged, rebased,
reset, force-pushed or cherry-picked** — verified in
`docs/agent-reports/baseline-release-evidence/01-git-state.txt`.

---

## 2. History relevant to this version

Read via the GitHub API because the sandbox workspace is a **depth-1 shallow
clone** (`git rev-parse --is-shallow-repository` → `true`), so local `git log`
shows one commit only. Full listing:
`docs/agent-reports/baseline-release-evidence/21-commit-history-v2-strict-mode.txt`.

| Commit | Date | Milestone |
|---|---|---|
| `758ba35` | 2026-08-19 | Initial commit |
| `faba32b` | 2026-08-19 | Backend + pgvector engine — **"43 passing tests"** |
| `8fb4a39` | 2026-08-19 | Three portals, docs, CI, DevOps — full MVP |
| `a847ad5` | 2026-08-19 | PM P0/P1 fix loop — **45 tests**, Postgres parity run, rate limiting |
| `61d13e9` | 2026-08-20 | V2 strict-mode prompts + audit guide (base of `docs/AUDIT_V2.md`) |
| `7a2e7fe`…`dd2c34d` | 2026-08-20 | V2 Phases 0A→5: research, security, perf, UI rebuild, dead keys, a11y |
| `0998ba4` | 2026-08-20 | Merge to `main` (current `main` HEAD) |
| `f7447d4` | 2026-08-20 | V3 realistic Persian dataset integration |
| `11e5a00` | 2026-08-21 | Agent master-prompt execution pack |
| `f97bfad` | 2026-08-21 | **Baseline commit** |

### 2.1 Correction issued during this audit — existing tags

An earlier step of this audit recorded "no tags exist", because local `git tag -l`
returns empty in a depth-1 shallow clone (tags pointing at unfetched commits are
not transferred, and `git fetch --all --prune` does not repair it). The remote was
re-queried directly and **the finding was wrong**:

```
$ git ls-remote --tags origin
v1.1-final-p0p1-fixed          -> a847ad5
v2-phase0-audit-complete       -> 7b16e4f
v2-phase2-performance          -> c3170a0
v2-phase3-ui                   -> 7bec5e3
v2-phase4-deadkeys             -> 87501f5
v2-final                       -> dd2c34d
v2-datasets-realistic          -> f7447d4
v2-datasets-realistic-merged   -> 939e05c
$ gh api …/releases --jq 'length'
0
```

The original wrong output and the correction are both retained verbatim in
`…/01-git-state.txt`. Corrected finding: **8 milestone tags exist, none is
SemVer-compliant, none points at the baseline commit `f97bfad`, none has a
GitHub Release or release notes, and the most recent (`v2-datasets-realistic-merged`)
is 4 commits behind the baseline.** The versioning recommendation in
`docs/ROLLBACK_AND_VERSIONING.md` is unchanged in substance: the baseline still
has no immutable reference of its own.

This history explains the single biggest documentation defect in the repository:
**three different test counts (43 / 45 / 97) are asserted simultaneously**, each
correct for a different commit, none labelled with the commit it was measured at.

---

## 3. Environment of record

Evidence: `docs/agent-reports/baseline-release-evidence/00-environment.txt`

| Component | Version / status |
|---|---|
| OS / kernel | Linux `6.1.158+` x86_64 (e2b sandbox), 2 vCPU, 3.8 GiB RAM |
| Node.js | **v22.22.3** (CI targets Node 22 — matches) |
| npm | **10.9.8** |
| Python (system) | **3.11.2** |
| Python (venv used for all backend runs) | **3.11.2** — `backend/.venv` |
| pip | 26.2.1 (upgraded from 23.0.1 inside the venv) |
| Docker / Docker Compose | **NOT INSTALLED** — `docker: command not found` |
| PostgreSQL client/server | **NOT INSTALLED** — `psql: command not found` |
| Redis server | **NOT INSTALLED** — `redis-server: command not found` |
| Chrome / Chromium | **NOT INSTALLED** (Lighthouse and Playwright cannot run) |
| git | 2.39.5 |
| gh | 2.23.0 |

**Version mismatch to note:** `ci/github-ci.yml` pins Python **3.12**;
`backend/pyproject.toml` requires `>=3.11`; this audit ran on **3.11.2**. The
suite is green on 3.11 but the 3.12 result is unverified here.

### 3.1 Network egress profile

| Destination | Result |
|---|---|
| `https://pypi.org/simple/` | 200 — **allowed** |
| `https://registry.npmjs.org/` | 200 — **allowed** |
| `https://github.com` | 200 — **allowed** |
| `https://huggingface.co` | 000 (TLS reset) — **blocked** → no real CLIP weights |
| `https://generativelanguage.googleapis.com` | 000 (TLS reset) — **blocked** → no real Gemini extraction |
| `https://www.digikala.com`, `https://torob.com` | 000 (TLS reset) — **blocked** → no seller-link liveness |

Every BLOCKED item in §5 traces back to this table, not to a defect in the code.

---

## 4. Runtime / data engine matrix used for this audit

Distinguishing the four evidence classes is a hard requirement of Master Prompt 01.

| Class | Definition | Used in this audit? |
|---|---|---|
| **MOCK** | Deterministic offline stand-in (`AI_PROVIDER=mock`, `EMBEDDING_BACKEND=hash`, `fakeredis`, `PAYMENT_PROVIDER=mock`) | **Yes — this is the only class exercised.** |
| **LOCAL** | Real process on this machine, SQLite + fakeredis | Yes — uvicorn boot, seed, API smoke |
| **STAGING** | Real Postgres 16 + pgvector, real Redis, sandbox PSP, real AI keys | **No — impossible here (no Docker/PG/Redis, no egress)** |
| **PRODUCTION** | Real customer traffic | **No** |

> **Client-facing consequence:** every performance, AI-accuracy and
> Postgres-parity number currently in this repository is either (a) MOCK/LOCAL,
> or (b) a STAGING number captured on **2026-08-19 at commit `a847ad5`** and
> never re-verified since. No number in this repository is PRODUCTION evidence.

---

## 5. Verification results at `f97bfad`

All commands were run from the repository root unless stated. Evidence files live
in `docs/agent-reports/baseline-release-evidence/`.

### 5.1 PASS — executed and green

| # | Check | Exact command | Result | Evidence |
|---|---|---|---|---|
| 1 | Backend dependency install | `python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt` | exit 0 — 65 packages installed | `02-backend-pip-install.log` |
| 2 | Backend test suite | `cd backend && .venv/bin/python -m pytest tests/ -v --tb=short` | **97 passed, 1 warning in 15.44s** (exit 0) | `03-backend-pytest.log` |
| 3 | Frontend dependency install | `cd frontend && npm ci` | exit 0 — 163 packages, **0 vulnerabilities** | `04-frontend-npm-ci.log` |
| 4 | Frontend strict build | `cd frontend && npm run build` (`tsc -b && vite build`) | exit 0 — built in 900 ms, 0 TS errors | `05-frontend-build.log` |
| 5 | Frontend lint | `cd frontend && npm run lint` (oxlint) | exit 0 — **0 errors, 12 warnings**, 49 files | `06-frontend-oxlint.log` |
| 6 | npm supply-chain audit | `cd frontend && npm audit` | **0 vulnerabilities** | `09-frontend-npm-audit.json` |
| 7 | AI extraction benchmark (**MOCK**) | `cd backend && AI_PROVIDER=mock .venv/bin/python scripts/evaluate_extraction.py` | exit 0 — 50 images, mean accuracy **100.0%**, 50/50 ≥0.8 | `10-ai-extraction-benchmark-mock.log` |
| 8 | Embedding service sanity | `cd backend && EMBEDDING_BACKEND=hash .venv/bin/python -m ai.embedding_service` | exit 0 — `backend=hash dim=512 load+embed=0.00s / OK` | `11-ai-embedding-service.log` |
| 9 | Seed (SQLite, hash embeddings) | `cd backend && DATABASE_URL=sqlite:///./baseline_audit.sqlite3 EMBEDDING_BACKEND=hash .venv/bin/python scripts/seed_products.py` | exit 0 — **seeded 100 products** + demo accounts | `12-seed-products-sqlite.log` |
| 10 | API boot + smoke (LOCAL) | `uvicorn app.main:app --host 0.0.0.0 --port 8000` then curl | startup complete; `GET /api/v1/health` served; `POST /api/v1/auth/login` → **200**; `GET /api/v1/products` unauthenticated → **401**; full security-header set present on a 404 | `18-api-smoke.log` |
| 11 | Live API surface inventory | `curl /openapi.json` + diff against `docs/API.md` | 29 paths / 39 operations enumerated | `19-api-endpoint-inventory.log` |
| 12 | Dead-keys audit (re-run) | `npx tsx scripts/auditDeadKeys.ts` | exit 0 — 31 files, 92 interactive elements, **0 DEAD, 0 PARTIAL** | `15-deadkeys-audit.log` |
| 13 | Secret & hygiene scan | `python3 scripts/audit_secrets.py --json …` | **PASS** — 244 files (210 pre-existing + this stage's 34), **0 findings**, 0 forbidden paths, 0 oversized files, 41 acknowledged placeholders | `17-secret-scan.txt` / `.json` |
| 14 | Clean-tree check | `git status --porcelain` before edits | clean; no stray artifacts; `.gitignore` covers `.venv`, `dist`, `__pycache__`, caches | `01-git-state.txt` |

### 5.2 FAIL — executed and red (real defects at HEAD)

| # | Check | Exact command | Result | Evidence |
|---|---|---|---|---|
| F-1 | Backend lint (the CI gate) | `cd backend && .venv/bin/ruff check app ai scripts` | **exit 1 — 3 errors**: `I001` unsorted imports in `app/api/routes/projects.py:2`; `E401` multiple imports on one line + `I001` in `scripts/seed_perf_products.py:16` | `07-backend-ruff.log` |
| F-2 | Python supply-chain audit | `cd backend && .venv/bin/pip-audit -r requirements.txt` | **exit 1 — 1 known vulnerability**: `ecdsa 0.19.2` / `PYSEC-2026-1325`, **no fix version available** (transitive via `python-jose[cryptography]`) | `08-backend-pip-audit.log` |
| F-3 | Alembic on the documented SQLite fallback | `cd backend && DATABASE_URL=sqlite:///./x.sqlite3 .venv/bin/alembic upgrade head` | **exit 1** — `NotImplementedError: No support for ALTER of constraints in SQLite dialect` raised by `alembic/versions/0003_product_feedback.py:46` (`op.create_unique_constraint`) | `14-alembic-upgrade-sqlite.log` |
| F-4 | Documentation link / file-reference audit | `python3 scripts/audit_docs_links.py --json …` | **FAIL — 0 broken markdown links, 5 missing file references**: `backend/seed_data/embeddings_real.json` ×3, `.env.example.v2` ×2 — all five are in documents owned by other agents. (The seven governance reports added by this stage are excluded from the file-reference check by default because they exist to *list* missing paths; `--include-reports` shows those 14 intentional citations.) | `16-docs-link-audit.txt` / `.json` |
| F-5 | Documentation claim verification | see `22-doc-claim-verification.txt` | **9 stale/contradictory claims** — full register in §6 | `22-doc-claim-verification.txt` |

`F-1` is a **CI-breaking defect**: `ci/github-ci.yml` runs `ruff check app ai scripts`
as a required backend step, so the workflow would fail on its first run.

### 5.3 BLOCKED — could not be executed here

Each row states the exact command, the exact blocker and what is required to
unblock it. **None of these may be reported as passing.**

| # | Check | Exact command | Exact blocker | Required to unblock |
|---|---|---|---|---|
| BL-1 | Postgres + pgvector parity | `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend sh -c "alembic upgrade head && pytest tests/ -v"` | `/bin/bash: line 1: docker: command not found`; `psql: command not found` | A host with Docker + Compose, or a reachable PostgreSQL 16 with the `vector` extension |
| BL-2 | Real Redis behaviour (shared blacklist / rate limit) | `REDIS_URL=redis://localhost:6379/0 pytest tests/` | `redis-server: command not found` | A Redis 7 instance |
| BL-3 | Real-model AI extraction ≥80% | `cd backend && AI_PROVIDER=gemini GEMINI_API_KEY=… .venv/bin/python scripts/evaluate_extraction.py --real --sample 10` | `generativelanguage.googleapis.com` unreachable (TLS reset, HTTP 000) **and** no API key is available to this agent | Egress to the provider + a client-supplied `GEMINI_API_KEY` / `OPENAI_API_KEY` |
| BL-4 | Real CLIP embeddings | `cd backend && .venv/bin/python scripts/seed_products.py --real-embeddings` | `huggingface.co` unreachable (HTTP 000); `torch`/`sentence-transformers` are commented out in `backend/requirements.txt` | Networked machine, ~600 MB model download, uncommented AI extras |
| BL-5 | Seller-link liveness | `DATABASE_URL=sqlite:///./baseline_audit.sqlite3 backend/.venv/bin/python scripts/check_links.py` | **Ran, exit 1** — `link check failed for https://torob.com/: TLS/SSL connection has been closed (EOF)`; result `0/100 links valid`. This is an egress artifact, **not** proof the links are dead | Public internet egress from the deploy host |
| BL-6 | Lighthouse ≥80 / LCP <3 s | `npx lighthouse http://localhost:4173/ --output=json` | No Chrome/Chromium binary in the sandbox | CI runner or a host with headless Chrome |
| BL-7 | Playwright E2E (`deadKeys.spec.ts`) | `cd frontend && npx playwright test` | No browsers installed; **`package.json` also has no `test` script** | `npx playwright install --with-deps` + a wired npm script |
| BL-8 | Docker image build | `docker-compose build` | `docker: command not found` | Docker host |
| BL-9 | Full-history git verification | `git log --all`, `git fsck` | Workspace is a depth-1 shallow clone | `git fetch --unshallow` (mitigated here via the GitHub API) |
| BL-10 | Enabling CI | `./scripts/enable_ci.sh` (pushes `.github/workflows/ci.yml`) | The GitHub App token used by agents **cannot push workflow files** (`refusing to allow a GitHub App … without 'workflows' permission`). This agent deliberately did not attempt it — it is also outside Prompt 01's allowed scope | A human/PAT with `workflow` scope, or granting the App the `workflows` permission |

---

## 6. Documentation Accuracy Register

Master Prompt 01 restricts this agent to `README.md`, `.env.example`, `.gitignore`,
`scripts/**` (audit tooling) and new `docs/**` files. Documents owned by other
agents (Prompt 07 owns deployment docs, Prompt 03 security docs, Prompt 04 AI/data
docs, Prompt 08 QA docs) were **not edited**; every defect found in them is
recorded here and mirrored into `integration-request.md`.

| ID | File:line | Claim as written | Measured truth at `f97bfad` | Action taken |
|---|---|---|---|---|
| D-1 | `README.md:71` (was) | "43 tests" | **97 passed** | **FIXED** — corrected + per-file breakdown table added |
| D-2 | `README.md:43` (was) | "the full 45-test suite passes against real Postgres+pgvector" | 45 was true at `a847ad5` (2026-08-19); today 97; the Postgres run has **not** been repeated | **FIXED** — reworded to "previously evidenced at `a847ad5`, currently unverified at HEAD" |
| D-3 | `README.md:26` (was) | "seeds 100 products … on first boot" | `docker-compose.yml` boots `load_realistic_products.py --expand-to 150`; the 100-product generator is the *non-Docker* path | **FIXED** |
| D-4 | `README.md:39` | "`--from-json` with the **committed** `backend/seed_data/embeddings_real.json`" | The file **does not exist** in the repository (`git ls-files` confirms) | **FIXED** in README; the same false claim remains in `docs/ARCHITECTURE.md:64`, `docs/DEPLOYMENT.md:28`, `docs/reports/ACCEPTANCE_REPORT.md:13` → **IR-003** |
| D-5 | `ci/README.md:13` | "backend pytest (43 tests)" | 97 | **IR-003** (CI docs are Prompt 07 scope) |
| D-6 | `docs/reports/ACCEPTANCE_REPORT.md:9,11,29,54`, `docs/reports/postgres_parity.md:52,55`, `docs/RESEARCH_V2.md:5`, `docs/WALKTHROUGH.md:67`, `docs/DESIGN_SYSTEM.md:22`, `docs/ARCHITECTURE.md:188` | "45/45", "43 automated tests" | 97 | **IR-003** — each needs an "as measured at commit X" stamp |
| D-7 | `docs/DEPLOYMENT.md:114`, `docs/DATASETS_AUDIT.md:49` | references `.env.example.v2` | **No such file exists**; only `.env.example` | **IR-003** |
| D-8 | `docs/AUDIT_V2.md:12-30` | "scanned 21 files, 55 interactive elements … 2 PARTIAL" | Re-run at HEAD: **31 files, 92 elements, 0 DEAD, 0 PARTIAL** | **IR-003** — stale but *better* than documented; must be re-stamped, not deleted |
| D-9 | `docs/API.md` | endpoint reference | Omits the entire `/feedback` resource (`GET`/`POST`/`DELETE`) and `GET /health`; live surface is 29 paths / 39 operations | **IR-003** |
| D-10 | `Caddyfile` CSP `img-src` | allows `https://*.s3.ir-thr1.arvanstorage.ir` | `.env.example` / `docs/DEPLOYMENT.md` use endpoint `s3.ir-**thr-at1**.arvanstorage.ir` — the CSP host pattern does **not** match the documented bucket host, so production images would be CSP-blocked | **IR-005** (Caddyfile is Prompt 07 scope) |
| D-11 | `.env.example` | 8 variables that no source file reads | `STORAGE_PROVIDER`, `CDN_URL`, `CORS_ORIGINS`, `VITE_API_URL`, `ZARINPAL_SANDBOX`, `ZARINPAL_CALLBACK_URL`, `RESEND_FROM_EMAIL`, `RESEND_FROM_NAME` — 0 references across `backend/app`, `backend/ai`, `backend/scripts`, `frontend/src`, `frontend/vite.config.ts`, `frontend/Dockerfile` | **FIXED** — each is now explicitly labelled `[UNUSED@f97bfad]` with its superseding variable; **IR-004** proposes wiring or removal |
| D-12 | `.env.example` | missing 2 real settings | `JWT_ALGORITHM`, `HNSW_EF_SEARCH` exist in `backend/app/core/config.py` but were undocumented | **FIXED** — added at their code defaults (`HS256`, `400`) |

---

## 7. Production blockers

Ordered by severity. "Owner" is the master prompt that owns the fix.

| ID | Severity | Blocker | Evidence | Owner |
|---|---|---|---|---|
| **B-1** | **Critical** | **Hardcoded demo accounts are seeded unconditionally, including in production.** `docker-compose.yml` runs `load_realistic_products.py … --if-empty` on every backend start; `ensure_default_accounts()` creates `admin@smartdecor.dev / Admin123!` (plus designer and homeowner) with **no `APP_ENV` guard**. `config.validate_runtime()` guards `SECRET_KEY`, `REDIS_URL` and `COOKIE_SECURE` — but not this. A production deployment ships with a publicly documented admin password. | `backend/scripts/load_realistic_products.py:108-118` (called at `:129` and `:137`), `backend/scripts/seed_products.py:229-238`, `docker-compose.yml:44-47`, `README.md` demo table | Prompt 03 (security) — **IR-001** |
| **B-2** | **High** | **CI has never run.** The canonical workflow lives at `ci/github-ci.yml`, not `.github/workflows/`. No status check gates any merge; the 97-test suite, the ruff gate and the Lighthouse budget are all advisory today. | `ci/README.md`, absence of `.github/`, `gh api` shows no workflow runs | Prompt 07 — **IR-006** |
| **B-3** | **High** | **The CI backend job would fail on its first run** because `ruff check app ai scripts` exits 1 (3 errors). Enabling CI without fixing F-1 produces an immediately red pipeline. | `07-backend-ruff.log` | Prompt 04/07 — **IR-002** |
| **B-4** | **High** | **No frontend test execution exists.** `frontend/package.json` defines `dev`, `build`, `lint`, `preview` — no `test`. The only spec, `frontend/tests/e2e/deadKeys.spec.ts`, is never executed by any documented command or by CI. | `frontend/package.json`, `ci/github-ci.yml` | Prompt 08 (QA) — **IR-007** |
| **B-5** | **High** | **No real-model AI evidence exists anywhere.** 100% extraction accuracy is a MOCK heuristic against its own ground truth. The contracted acceptance criterion ("≥80% on 50 images") has never been measured with a real provider. | `10-ai-extraction-benchmark-mock.log`, `docs/reports/extraction_report.json` (`"mode": "MOCK"`) | Prompt 04 — client key required |
| **B-6** | **Medium** | **Postgres/pgvector parity is stale.** Last verified 2026-08-19 at `a847ad5` with 45 tests; 52 tests have been added since. The production data engine is therefore untested at HEAD. | `docs/reports/postgres_parity.md`, `03-backend-pytest.log` | Prompt 07/08 — **BL-1** |
| **B-7** | **Medium** | **`alembic upgrade head` is Postgres-only.** It fails on SQLite at revision `0003`. Consequence: the SQLite path is provisioned by `create_all()`, so **migration/model drift is structurally undetectable** in every dev and CI run that does not use Postgres. | `14-alembic-upgrade-sqlite.log` | Prompt 04/07 — **IR-002** |
| **B-8** | **Medium** | **Unfixable dependency CVE in the tree.** `ecdsa 0.19.2` (`PYSEC-2026-1325`) has **no fix version**. It is pulled in by `python-jose[cryptography]`. | `08-backend-pip-audit.log` | Prompt 03 — **IR-008** |
| **B-9** | **Medium** | **Python dependencies are unpinned.** `backend/requirements.txt` uses `>=` for all 20 direct dependencies with no lock/constraints file, so two installs a week apart can resolve to different trees. See `docs/REPRODUCIBILITY.md`. | `backend/requirements.txt`, `20-backend-pip-freeze.txt` | Prompt 07 — **IR-009** |
| **B-10** | **Medium** | **Seller links are unverified.** 100 catalog links returned 0/100 valid here purely because egress is blocked, and the shipped catalog links are sample/derived URLs, not a live feed. Acceptance criterion #6 remains open. | `13-seller-link-check.log`, `docs/DATASETS_AUDIT.md` | Prompt 06 — deploy-host run |
| **B-11** | **Low** | **CSP host mismatch** would block production product images (D-10). | `Caddyfile`, `.env.example` | Prompt 07 — **IR-005** |
| **B-12** | **Low** | **No SemVer tag on the baseline, no CHANGELOG, no GitHub Release.** 8 ad-hoc milestone tags exist (`v2-final`, `v2-phase3-ui`, …), but none is SemVer, none points at `f97bfad`, and 0 Releases are published — so the baseline has no immutable reference to roll back to. | `git ls-remote --tags origin`, `gh api …/releases` → 0 | This stage — see `docs/ROLLBACK_AND_VERSIONING.md` |

---

## 8. Remaining risks

| ID | Risk | Likelihood | Impact | Mitigation / owner |
|---|---|---|---|---|
| R-1 | Client demos a "production-ready" build and an attacker logs in as `admin@smartdecor.dev` | High if deployed as-is | Critical | B-1 / IR-001 before any public host |
| R-2 | Real Gemini/OpenAI extraction lands well below 80%, invalidating the headline AI claim | Medium | High — contractual | Run BL-3 on the deploy host **before** the acceptance meeting; human-in-the-loop review already exists as the fallback |
| R-3 | Postgres-only behaviour (HNSW recall, `<=>` semantics, pool limits) regresses undetected because CI/tests default to SQLite | Medium | High | BL-1 in CI on every PR (IR-006) |
| R-4 | Unpinned Python deps break a future build (e.g. a breaking `pydantic`/`starlette` release) | Medium | Medium | IR-009 constraints file |
| R-5 | `ecdsa` CVE remains unpatched upstream | High | Medium | IR-008 — evaluate `pyjwt` migration to drop `python-jose`/`ecdsa` |
| R-6 | Stale reports (45 tests, 21-file dead-key scan) are quoted to the client and later contradicted | High while unfixed | High — credibility | §6 register + IR-003 |
| R-7 | Dataset is a deterministic 150-row expansion of 20 curated rows presented as a catalog | Medium | Medium | Already disclosed in `docs/DATASETS_AUDIT.md`; keep the disclosure in every client artifact |
| R-8 | Unsplash imagery is not licensed for the client's commercial use | Medium | Medium | `docs/CLIENT_DATASETS_REQUEST.md` — client must supply licensed assets |
| R-9 | `main` is 7 commits behind `v2-strict-mode`; a contributor branching from `main` gets a stale tree | Medium | Medium | Prompt 10 to reconcile, or set `v2-strict-mode` as the GitHub default branch |
| R-10 | Fernet "encryption at rest" is an application-level abstraction, not a managed KMS | Low | Medium | Documented in ADR-008; production KMS decision required from the client |

---

## 9. Client decisions and dependencies

Nothing below can be resolved by an engineering agent — each needs the client.

| ID | Decision / dependency needed | Blocks |
|---|---|---|
| C-1 | Provide a `GEMINI_API_KEY` (or `OPENAI_API_KEY`) for a real 50-image extraction benchmark | B-5, acceptance criterion #4 |
| C-2 | Confirm the production data engine (managed PostgreSQL 16 + pgvector vs self-hosted) and provide the instance | B-6, BL-1 |
| C-3 | Provide the real Zarinpal merchant ID and the production HTTPS callback origin | Payment go-live |
| C-4 | Provide object-storage credentials (Arvan / Liara / AWS) and confirm the CDN base URL | Image hosting, D-10/IR-005 |
| C-5 | Supply the **real product catalog** (SKU, price, stock, product-level URL, licensed imagery) — the shipped 150 rows are demo data | B-10, R-7, R-8 |
| C-6 | Confirm the production domain so Caddy can provision Let's Encrypt certificates | TLS go-live |
| C-7 | Decide whether demo accounts may exist in production at all; if yes, supply the rotation policy | B-1 |
| C-8 | Grant the GitHub App the `workflows` permission **or** nominate a human to run `./scripts/enable_ci.sh` | B-2 |
| C-9 | Approve the versioning scheme and the initial tag `v1.2.0-baseline` proposed in `docs/ROLLBACK_AND_VERSIONING.md` | B-12 |
| C-10 | Provide a Resend API key and a verified sending domain | Share-with-client email |
| C-11 | Confirm data-residency / GDPR posture and the log-retention period for `audit_logs` | Compliance sign-off |

---

## 10. Recommended next agents and execution order

Wave 1 of `agent-master-prompts/00-README.md` is otherwise parallel-safe; these
two exceptions are sequencing constraints discovered by this audit.

| Order | Agent | Why now | Must fix |
|---|---|---|---|
| 1 | **03 — Security & Privacy** | B-1 is the only Critical finding and it is a one-file guard | IR-001 (env-gate demo accounts), IR-008 (`ecdsa`) |
| 2 | **07 — Infrastructure / CI / Observability** | Nothing else can be *proved* until CI runs against Postgres | IR-002, IR-005, IR-006, IR-009; re-run BL-1 |
| 3 | **04 — AI / Recommender / Data** | Owns the ruff error in `projects.py`, the SQLite-hostile migration and the real-model benchmark | IR-002, B-5/BL-3 (needs C-1), IR-003 for AI docs |
| 4 | **08 — QA & Acceptance Testing** | Frontend has no executable test path | IR-007, Playwright + Lighthouse in CI |
| 5 | **02 — Research**, **05 — Frontend/RTL**, **06 — Integrations** | Independent; safe to run in parallel with 3–4 | 06 owns the seller-link run (B-10) |
| 6 | **09 — Sales & Demo Documentation** | Must not start before §6 is cleared, or the deck will quote retracted numbers | Consume this document as its source of truth |
| 7 | **10 — Integration & Release Manager** | Final merge, tag `v1.2.0-baseline`, CHANGELOG | `docs/ROLLBACK_AND_VERSIONING.md` |

---

## 11. Evidence index

All paths relative to `docs/agent-reports/baseline-release-evidence/`.

| File | Contents |
|---|---|
| `00-environment.txt` | OS, Node, npm, Python, pip, docker/psql/redis absence, egress probe |
| `01-git-state.txt` | HEAD, `git log -1 --format=fuller`, status, shallow flag, branch list, remote branch SHAs |
| `02-backend-pip-install.log` | Full `pip install -r requirements.txt` transcript |
| `03-backend-pytest.log` | Full `pytest -v --tb=short` transcript — 97 passed |
| `04-frontend-npm-ci.log` | `npm ci` — 163 packages, 0 vulnerabilities |
| `05-frontend-build.log` | `tsc -b && vite build` — full chunk listing |
| `06-frontend-oxlint.log` | oxlint — 0 errors, 12 warnings |
| `07-backend-ruff.log` | ruff — **3 errors** (CI-breaking) |
| `08-backend-pip-audit.log` | pip-audit — `ecdsa` `PYSEC-2026-1325` |
| `09-frontend-npm-audit.json` | `npm audit --json` |
| `10-ai-extraction-benchmark-mock.log` | MOCK 50-image benchmark — 100% |
| `11-ai-embedding-service.log` | hash backend, 512-dim sanity check |
| `12-seed-products-sqlite.log` | 100-product SQLite seed |
| `13-seller-link-check.log` | `check_links.py` — 0/100, TLS blocked by sandbox egress |
| `14-alembic-upgrade-sqlite.log` | Full traceback of the SQLite migration failure |
| `15-deadkeys-audit.log` | `auditDeadKeys.ts` re-run — 31 files, 92 elements, 0 DEAD |
| `16-docs-link-audit.txt` / `.json` | Documentation link + file-reference audit |
| `17-secret-scan.txt` / `.json` | Secret & hygiene scan, incl. the acknowledged-placeholder list |
| `18-api-smoke.log` | Live `/health`, auth, authz and security-header responses |
| `19-api-endpoint-inventory.log` | 39 live operations vs `docs/API.md` |
| `20-backend-pip-freeze.txt` | Exact resolved dependency tree of this audit (87 packages) |
| `21-commit-history-v2-strict-mode.txt` | Full branch history via the GitHub API |
| `22-doc-claim-verification.txt` | Measured-vs-documented comparison behind §6 |

---

## 12. Companion documents

| Document | Purpose |
|---|---|
| `docs/RELEASE_CHECKLIST.md` | The gate that must be green before a release is cut |
| `docs/ROLLBACK_AND_VERSIONING.md` | SemVer policy, tagging, rollback runbook, ownership matrix |
| `docs/REPRODUCIBILITY.md` | Can a third party rebuild this from a clean clone? |
| `docs/agent-reports/baseline-release-report.md` | This stage's agent report and Release Manager decision |
| `integration-request.md` | Out-of-scope fixes handed to the owning agents |
