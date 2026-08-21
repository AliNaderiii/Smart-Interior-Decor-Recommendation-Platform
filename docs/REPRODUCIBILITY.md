# Repository Reproducibility Assessment

Baseline: `f97bfad` · Assessed 2026-08-21 · Owner: Master Prompt 01.

**Question answered here:** if a third party clones this repository onto a clean
machine and follows only the committed documentation, do they get the same
working system — and the same numbers?

**Verdict: PARTIALLY REPRODUCIBLE.** The offline development profile reproduces
reliably from a clean clone. The production profile does not, for four concrete
reasons (§4, §5, §6, §7).

---

## 1. Scoring

| Dimension | Score | Basis |
|---|---|---|
| Source completeness | **Good** | 210 tracked files at the baseline commit; the application builds and runs with nothing fetched from outside the package registries |
| Frontend dependency determinism | **Good** | `package-lock.json` committed, `npm ci` exit 0, 163 packages, 0 vulnerabilities |
| Backend dependency determinism | **Poor** | All 20 direct dependencies use `>=` ranges; no lock or constraints file (§4) |
| Container determinism | **Poor** | Floating base image tags; no digests (§5) |
| Documented-command accuracy | **Fair** | Corrected in `README.md`; contradictions remain in other agents' docs (`docs/RELEASE_BASELINE.md` §6) |
| Test reproducibility | **Good (dev) / Unknown (prod)** | 97/97 on SQLite+fakeredis; Postgres path unverified at HEAD |
| Data reproducibility | **Good** | Deterministic seeds (`random.seed(42)`, deterministic 150-row expansion), all inputs committed |
| Evidence reproducibility | **Fair** | Every claim in `docs/RELEASE_BASELINE.md` has a re-runnable command; four acceptance numbers are environment-blocked |

---

## 2. What was reproduced, exactly

Executed on a clean sandbox (Debian, kernel 6.1.158+, 2 vCPU, 3.8 GiB) starting
from a fresh clone. Full transcripts in
`docs/agent-reports/baseline-release-evidence/`.

```bash
# 1. Backend from scratch
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt          # exit 0
cd backend && .venv/bin/python -m pytest tests/ -v --tb=short      # 97 passed in 15.44s

# 2. Frontend from the lockfile
cd frontend && npm ci                                              # exit 0, 163 packages
npm run build                                                      # exit 0, built in 900ms
npm run lint                                                       # exit 0, 12 warnings

# 3. Offline data + AI path
cd backend
DATABASE_URL=sqlite:///./x.sqlite3 EMBEDDING_BACKEND=hash \
  .venv/bin/python scripts/seed_products.py                        # seeded 100 products
AI_PROVIDER=mock .venv/bin/python scripts/evaluate_extraction.py   # 50 images, 100.0%
EMBEDDING_BACKEND=hash .venv/bin/python -m ai.embedding_service    # backend=hash dim=512, OK

# 4. Runtime
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000          # Application startup complete
curl -s -o /dev/null -w '%{http_code}' localhost:8000/api/v1/auth/login ...   # 200
```

Every one of those steps succeeded on the first attempt with no undocumented
workaround. That is the reproducible core.

---

## 3. Environment prerequisites the docs do not state

The documented quick start assumes a machine that has these. A clean CI container
often does not.

| Prerequisite | Documented? | Notes |
|---|---|---|
| Python ≥3.11 | Partially | `pyproject.toml` says `>=3.11`; `README.md` says only "python"; CI pins 3.12. Audited on 3.11.2 |
| Node 22 | No | Only `ci/github-ci.yml` states it; `README.md` does not |
| Docker + Compose v2 | Yes | `README.md` quick start |
| `npm ci` vs `npm install` | **Was not** | `README.md` said `npm install`, which ignores the lockfile — **fixed in this stage** |
| C toolchain for `psycopg[binary]` | N/A | Wheels are available; no build step needed on linux x86_64 |
| ~600 MB HuggingFace download for CLIP | Yes | `docs/DEPLOYMENT.md` §1 |
| Headless Chrome for Lighthouse | Partially | Implied by the command, never stated as a prerequisite |

---

## 4. Reproducibility gap #1 — unpinned Python dependencies

`backend/requirements.txt` declares every dependency as a lower bound:

```
fastapi>=0.115      pydantic>=2.7      sqlalchemy>=2.0.30
alembic>=1.13       redis>=5.0         boto3>=1.34        ... (20 total)
```

Two installs a week apart can resolve to different trees, so "97 tests pass" is
not a statement about a reproducible artifact. The exact tree that produced this
audit's results is captured in
`docs/agent-reports/baseline-release-evidence/20-backend-pip-freeze.txt`
(87 packages), including notable resolutions:

| Package | Resolved here |
|---|---|
| fastapi | 0.141.1 |
| pydantic | 2.13.4 |
| sqlalchemy | 2.0.52 |
| alembic | 1.19.1 |
| starlette | 1.6.0 |
| redis | 8.1.0 |
| numpy | 2.4.6 |
| pgvector | 0.5.0 |
| psycopg / psycopg-binary | 3.3.4 |
| bcrypt | 4.0.1 (bounded by `bcrypt<4.1`) |
| pytest | 9.1.1 |

**Recommended fix (IR-009, Prompt 07):** keep `requirements.txt` as the human
intent file and add a generated `backend/requirements.lock.txt`
(`pip-compile` / `pip freeze`) that CI and Docker install from.

---

## 5. Reproducibility gap #2 — floating container images

`docker-compose.yml` and `ci/github-ci.yml` reference:

- `ankane/pgvector:latest` — **`latest`**, so the Postgres *and* pgvector version can change under the project silently (the parity report claims pgvector 0.6.2; nothing pins it)
- `redis:7-alpine`
- `caddy:2-alpine`

**Recommended fix (IR-011, Prompt 07):** pin by digest, e.g.
`ankane/pgvector:v0.5.1-pg16@sha256:…`, and record the digests in the release notes.

---

## 6. Reproducibility gap #3 — the SQLite path never runs the migrations

`alembic upgrade head` fails on SQLite at revision `0003_product_feedback`:

```
NotImplementedError: No support for ALTER of constraints in SQLite dialect.
Please refer to the batch mode feature which allows for SQLite migrations
using a copy-and-move strategy.
  File ".../alembic/versions/0003_product_feedback.py", line 46, in upgrade
    op.create_unique_constraint(
```

Full traceback: `…/14-alembic-upgrade-sqlite.log`.

The SQLite path therefore builds its schema with `Base.metadata.create_all()`
inside the seed scripts. Two consequences:

1. **Migration/model drift is structurally undetectable** in every dev and CI run
   that does not use Postgres — the tests validate the ORM models, never the
   migration chain.
2. The Postgres-only migration chain is exercised **only** in the Docker/CI
   Postgres job, which has never run (B-2).

**Recommended fix (IR-002, Prompt 04/07):** wrap the constraint in
`op.batch_alter_table(...)` so SQLite is supported, **and** add a CI job that runs
`alembic upgrade head && alembic downgrade base && alembic upgrade head` against
Postgres.

---

## 7. Reproducibility gap #4 — four acceptance numbers cannot be reproduced anywhere in-repo

| Number quoted in the repository | Reproducible? |
|---|---|
| "45/45 tests on Postgres+pgvector, p95 1625 ms" | **No** — requires Docker/Postgres; and the suite is now 97 tests |
| "AI extraction ≥80% (real mode)" | **No** — requires a provider API key and egress |
| "Seller links 200 OK" | **No** — requires public internet egress |
| "Lighthouse ≥80, LCP <3 s" | **No** — requires headless Chrome |

Each is individually reasonable; together they mean **no single machine in the
project's documented toolchain can regenerate the acceptance report**. The fix is
organisational, not technical: CI (B-2) is the only environment where all four can
be produced, so enabling it is the highest-leverage reproducibility action
available.

---

## 8. Clean-clone reproduction script

Copy-pasteable end-to-end verification of everything that *is* reproducible today.

```bash
git clone https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform.git
cd Smart-Interior-Decor-Recommendation-Platform
git checkout f97bfad371c7a33cb4fe9f52b7c51520a363fb43

# --- backend ---
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
( cd backend && .venv/bin/python -m pytest tests/ -v --tb=short )        # expect: 97 passed
( cd backend && AI_PROVIDER=mock .venv/bin/python scripts/evaluate_extraction.py )   # expect: 100.0%, PASS
( cd backend && EMBEDDING_BACKEND=hash .venv/bin/python -m ai.embedding_service )    # expect: OK
( cd backend && .venv/bin/pip install ruff && .venv/bin/ruff check app ai scripts )  # KNOWN FAILURE: 3 errors

# --- frontend ---
( cd frontend && npm ci && npm run build && npm run lint )               # expect: build ok, 0 lint errors

# --- governance audits ---
python3 scripts/audit_secrets.py                                          # expect: PASS, 0 findings
python3 scripts/audit_docs_links.py                                       # KNOWN FAILURE: 6 missing refs
npx tsx scripts/auditDeadKeys.ts                                          # expect: 0 DEAD  (must run from repo root)

# --- requires Docker (not reproducible in the audit sandbox) ---
docker compose -f docker-compose.yml -f docker-compose.test.yml \
  run --rm backend sh -c "alembic upgrade head && pytest tests/ -v"
```

Known-failure lines are labelled deliberately: a reproduction script that hides
current defects is worse than none.

---

## 9. Priority actions to reach "fully reproducible"

| # | Action | Owner | Closes |
|---|---|---|---|
| 1 | Enable CI in `.github/workflows/` | 07 | B-2, gap §7 |
| 2 | Fix the 3 ruff errors so CI can go green | 04/07 | F-1, B-3 |
| 3 | Add `backend/requirements.lock.txt` and install from it in CI + Docker | 07 | gap §4 |
| 4 | Pin container images by digest | 07 | gap §5 |
| 5 | Make revision `0003` SQLite-compatible via `batch_alter_table` and add a migration round-trip job | 04/07 | gap §6, B-7 |
| 6 | Tag `v1.2.0-baseline` | 10 | B-12 |
| 7 | Re-run the Postgres parity suite at HEAD and re-stamp `docs/reports/postgres_parity.md` | 07/08 | B-6 |
