# Evidence — Stage 01, Baseline / Release Governance / Repository Hygiene

**Baseline commit:** `f97bfad371c7a33cb4fe9f52b7c51520a363fb43`
**Captured:** 2026-08-21 (UTC)
**Environment:** Linux 6.1.158+ x86_64 · Node v22.22.3 · npm 10.9.8 · Python 3.11.2 · no Docker / PostgreSQL / Redis / Chrome
**Report:** [`../baseline-release-report.md`](../baseline-release-report.md) · **Baseline:** [`../../RELEASE_BASELINE.md`](../../RELEASE_BASELINE.md)

Every file below is the **verbatim** stdout/stderr of the command named in its
header. Nothing was edited, trimmed or reformatted after capture. Failing outputs
are kept exactly as they failed.

| File | Command | Outcome |
|---|---|---|
| `00-environment.txt` | `uname -a`, `node -v`, `npm -v`, `python3 -V`, `docker --version`, `psql --version`, `redis-server --version`, `git --version`, `gh --version`, egress probes | informational |
| `01-git-state.txt` | `git rev-parse HEAD`, `git log -1 --format=fuller`, `git status`, `git branch -a`, `git tag -l`, `gh api …/branches` | informational |
| `02-backend-pip-install.log` | `backend/.venv/bin/pip install -r backend/requirements.txt` | **exit 0** |
| `03-backend-pytest.log` | `cd backend && .venv/bin/python -m pytest tests/ -v --tb=short` | **exit 0 — 97 passed** |
| `04-frontend-npm-ci.log` | `cd frontend && npm ci` | **exit 0 — 163 packages, 0 vulnerabilities** |
| `05-frontend-build.log` | `cd frontend && npm run build` | **exit 0 — 0 TS errors** |
| `06-frontend-oxlint.log` | `cd frontend && npm run lint` | **exit 0 — 0 errors, 12 warnings** |
| `07-backend-ruff.log` | `cd backend && .venv/bin/ruff check app ai scripts` | **exit 1 — 3 errors (CI-breaking)** |
| `08-backend-pip-audit.log` | `cd backend && .venv/bin/pip-audit -r requirements.txt` | **exit 1 — `ecdsa 0.19.2` / `PYSEC-2026-1325`, no fix** |
| `09-frontend-npm-audit.json` | `cd frontend && npm audit --json` | **0 vulnerabilities** |
| `10-ai-extraction-benchmark-mock.log` | `cd backend && AI_PROVIDER=mock .venv/bin/python scripts/evaluate_extraction.py` | **exit 0 — MOCK, 50 images, 100.0%** |
| `11-ai-embedding-service.log` | `cd backend && EMBEDDING_BACKEND=hash .venv/bin/python -m ai.embedding_service` | **exit 0 — dim 512, OK** |
| `12-seed-products-sqlite.log` | `cd backend && DATABASE_URL=sqlite:///./baseline_audit.sqlite3 EMBEDDING_BACKEND=hash .venv/bin/python scripts/seed_products.py` | **exit 0 — 100 products** |
| `13-seller-link-check.log` | `DATABASE_URL=sqlite:///./baseline_audit.sqlite3 backend/.venv/bin/python scripts/check_links.py` | **exit 1 — 0/100 valid; TLS blocked by sandbox egress, NOT proof of dead links** |
| `14-alembic-upgrade-sqlite.log` | `cd backend && DATABASE_URL=sqlite:///./baseline_alembic.sqlite3 .venv/bin/alembic upgrade head` | **exit 1 — `NotImplementedError` in revision `0003`** |
| `15-deadkeys-audit.log` | `npx tsx scripts/auditDeadKeys.ts` (from repo root) | **exit 0 — 31 files, 92 elements, 0 DEAD** |
| `16-docs-link-audit.txt` / `.json` | `python3 scripts/audit_docs_links.py --json …` | **FAIL — 0 broken links, 5 missing file references** |
| `17-secret-scan.txt` / `.json` | `python3 scripts/audit_secrets.py --json …` | **PASS — 244 files, 0 findings** |
| `18-api-smoke.log` | `curl` against a live `uvicorn app.main:app` (SQLite + fakeredis + mock AI) | login **200**, unauth products **401**, full security-header set |
| `19-api-endpoint-inventory.log` | `curl /openapi.json` + diff vs `docs/API.md` | 29 paths / 39 operations; `/feedback` and `/health` undocumented |
| `20-backend-pip-freeze.txt` | `cd backend && .venv/bin/pip freeze` | 87 resolved packages — the exact tree behind `03-backend-pytest.log` |
| `21-commit-history-v2-strict-mode.txt` | `gh api …/commits?sha=v2-strict-mode --paginate` | 26 commits (workspace is a depth-1 shallow clone) |
| `22-doc-claim-verification.txt` | measured-vs-documented comparison (test counts, catalog sizes, dead keys, API surface, `.env` parity, unused vars) | source data for the Documentation Accuracy Register |

## Reproducing this evidence

```bash
git checkout f97bfad371c7a33cb4fe9f52b7c51520a363fb43
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
( cd backend && .venv/bin/python -m pytest tests/ -v --tb=short )
( cd frontend && npm ci && npm run build && npm run lint )
python3 scripts/audit_secrets.py
python3 scripts/audit_docs_links.py
npx tsx scripts/auditDeadKeys.ts
```

See [`../../REPRODUCIBILITY.md`](../../REPRODUCIBILITY.md) §8 for the full
clean-clone script, including the steps that are expected to fail today.

## What is NOT in this directory, and why

| Missing evidence | Reason | Unblock |
|---|---|---|
| Postgres + pgvector test run | no Docker, no `psql` in the audit environment | run on a Docker host or in CI (IR-006) |
| Real Redis run | no `redis-server` | Redis 7 instance |
| Real-model AI extraction (`--real`) | provider endpoint unreachable **and** no API key | client key C-1 + egress |
| Real CLIP embeddings | `huggingface.co` unreachable; torch extras commented out | networked machine |
| Lighthouse report | no Chrome/Chromium | CI runner |
| Playwright E2E run | no browsers **and** no `npm test` script (IR-007) | QA stage |

**No placeholder, estimated or carried-forward result was written into this
directory.** If a check could not run, there is no file for it — only this table.
