# Smart Interior Decor Recommendation Platform

AI-powered living-room furnishing recommendations with explainability, editable
moodboards, a 2D floorplan preview, validated shopping lists, a designer (B2B2C)
portal, an admin portal with human-in-the-loop AI feature extraction, and a
Zarinpal-based Pro paywall. **MVP scope: living_room only.**

> **Release baseline.** The tree was first audited at commit `f97bfad` on
> 2026-08-21 ([`docs/RELEASE_BASELINE.md`](docs/RELEASE_BASELINE.md)) and
> re-audited at the Stage-1 HEAD on 2026-08-26
> ([`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md)).
> Re-verified at the current HEAD on 2026-09-01 in a clean sandbox
> (Python 3.13, Node 22.23.2): backend **598 passed / 22 skipped
> (620 collected)**, frontend **65 unit tests across 10 files**, strict build,
> lint and test typecheck clean, secret scan clean, docs link audit clean.
> Verified in CI at this HEAD (run
> [#33430375507](https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform/actions/runs/33430375507),
> 2026-08-31, all jobs green): the backend suite against **PostgreSQL 16 +
> pgvector and real Redis**, **Playwright E2E (29 tests, 4 role projects)**,
> **Lighthouse CI ≥80**, seller-link liveness over the 150-product catalog,
> `/recommend` p95 evidence, and Docker builds.
> Still not verified anywhere: real-model AI extraction accuracy (CI runs the
> `--real` benchmark only when a provider secret is configured).
> Read the checklist before quoting any number from this repository to a
> client.

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 19 · Vite · TypeScript (strict) · Tailwind CSS · Zustand · TanStack Query · react-grid-layout |
| Backend | Python · FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 · PyJWT · passlib[bcrypt] |
| Data | PostgreSQL 16 + pgvector (`vector(512)`, HNSW) · Redis |
| AI | CLIP ViT-B/32 embeddings (offline hash fallback) · Gemini / OpenAI vision extraction (provider-agnostic via `.env`) |
| Infra | Docker Compose · Caddy (TLS 1.3) · GitHub Actions CI |

## Quick start (one command)

```bash
cp .env.example .env          # then set SECRET_KEY, FERNET_KEY
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

→ App at `https://localhost` (Caddy, TLS 1.3) · API docs at `https://localhost/docs`.
The development overlay runs `alembic upgrade head` and then
`load_realistic_products.py --realistic --expand-to 150 --if-empty` before
serving, which seeds the **150-row Persian demo catalog** (hash embeddings;
`--if-empty` keeps it idempotent). Demo accounts are enabled only by the
development overlay (`SEED_DEMO_ACCOUNTS=true`); the production overlay never
enables them. **Production startup runs migrations only** — the catalog is
loaded deliberately via the one-shot bootstrap job
(`docker compose --profile bootstrap up catalog-bootstrap`), which requires the
real-embedding artefact and fails loudly if it is absent.
(`backend/scripts/seed_products.py`, which generates 100 synthetic products, is
the separate no-Docker path documented under *Local development*.)

### Demo accounts — development only

| Role | Email | Password |
|---|---|---|
| Homeowner | demo@smartdecor.dev | Demo1234! |
| Designer | designer@smartdecor.dev | Design123! |
| Admin | admin@smartdecor.dev | Admin123! |

> **How production is protected (B-1 / IR-001 — closed).** Demo logins exist
> only when `SEED_DEMO_ACCOUNTS=true` **and** `APP_ENV != production`; under
> `APP_ENV=production` the setting itself is rejected at boot by
> `Settings.validate_runtime()` — a production process that asks for demo
> accounts does not start at all (CI security probe +
> `scripts/prove_demo_refusal.sh`; re-verified by direct invocation on
> 2026-09-01). The old unconditional-seeding boot path was removed in Stage 04:
> startup is now migrations + server only, catalog loading is the explicit
> `catalog-bootstrap` profile job described above. The credentials in the table
> above live in exactly one audited place — `backend/app/core/demo_seed.py` —
> and are development-only by construction
> ([`docs/security/DEMO_ACCOUNTS.md`](docs/security/DEMO_ACCOUNTS.md)).

## Dev vs Production data engines — read this

| | Dev / CI | Production |
|---|---|---|
| Database | SQLite fallback (vector column degrades to JSON, cosine in Python) | **PostgreSQL 16 + pgvector required** — fused `<=>` query + HNSW index |
| Embeddings | deterministic 512-dim hash (offline, hermetic tests) | **real CLIP ViT-B/32** — `python scripts/seed_products.py --real-embeddings` once, or `--from-json` after generating the embeddings JSON at **backend/seed_data/embeddings_real.json** on a networked machine (**that file is not in this repository** — four other docs wrongly call it "committed"; see IR-003) |
| Extraction | `AI_PROVIDER=mock` heuristic | `AI_PROVIDER=gemini` (or `openai`) + API key; validate with `python scripts/evaluate_extraction.py --real` |
| Redis | in-process fakeredis (per-worker!) | real Redis (`REDIS_URL`) — shared cache, JWT blacklist and rate limiting |

Postgres parity was demonstrated on **2026-08-19 at commit `a847ad5`**, when the
suite contained 45 tests (`docs/reports/postgres_parity.md`). The suite has since
grown to **620 collected** (598 passed / 22 skipped, re-measured at HEAD on
2026-09-01) and that Postgres run has **not** been repeated locally — the
baseline audit environment has no Docker or PostgreSQL binary. Treat Postgres
parity as *previously evidenced, currently unverified at HEAD*; re-run it before
release:

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml \
  run --rm backend sh -c "alembic upgrade head && pytest tests/ -v"
```

## Local development (no Docker)

**Prerequisites:** Python ≥ 3.12 (CI runs 3.12; 3.13 also verified on
2026-09-01) and **Node ≥ 22** for the frontend. The locked jsdom/undici test
stack does not start on Node 20 (`webidl.util.markAsUncloneable is not a
function`); CI pins Node 22 and the repo ships a matching `.nvmrc`
(`nvm use`). `package.json` enforces this via `engines.node`.

```bash
# backend — SQLite + fakeredis fallback works out of the box
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/seed_products.py           # creates the schema via create_all() + 100 demo products
uvicorn app.main:app --reload --port 8000

# frontend (separate shell) — dev server proxies /api → :8000
cd frontend
npm ci                                    # npm ci, not npm install: package-lock.json is the lock of record
npm run dev
```

> Revision `0003_product_feedback` uses Alembic batch mode for its unique
> constraint. The migration chain now runs on both SQLite and PostgreSQL; the
> production validation target remains PostgreSQL 16 + pgvector. The dev seed
> script still uses `Base.metadata.create_all()` for a fast, isolated fixture
> setup, while CI and the test compose profile run the real migration chain.

## Tests & acceptance gates

Counts below were re-measured at the current HEAD on 2026-09-01 in a clean
sandbox (backend on Python 3.13, frontend on Node 22.23.2); the Stage-1 logs
live in
[`docs/agent-reports/stage1-evidence/final-sweep/`](docs/agent-reports/stage1-evidence/final-sweep/).
See [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md) for the full gate
status and [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md) for the dependency
policy.

### Backend

```bash
cd backend
pip install -r requirements.lock.txt      # the lockfile is the contract, not requirements.txt
pytest                                    # 598 passed, 22 skipped / 620 collected (SQLite + fakeredis + mock AI)
ruff check app ai scripts tests           # 0 errors

python scripts/verify_lock_install.py     # installed env == requirements.lock.txt
python scripts/audit_dependencies.py      # pip-audit the LOCKED set + expiring allowlist
python scripts/evaluate_extraction.py     # 50-image benchmark, >=80% required — MOCK mode, 100%
python scripts/evaluate_recommender.py --compare-profiles   # weight-profile comparison (C-6)
python -m ai.embedding_service            # backend=hash dim=512 sanity check
```

The 22 skips are the PostgreSQL- and real-Redis-gated tests, which run in the
CI `backend` job against Postgres 16 + pgvector.

### Frontend

```bash
cd frontend
npm ci                                    # not npm install: package-lock.json is the lock of record

npm test                                  # Vitest + Testing Library — 65 tests, 10 files (Node ≥22 required)
npm run lint                              # oxlint — 0 errors, 12 warnings
npm run build                             # tsc strict + vite — 0 errors
npx tsc -p tsconfig.tests.json            # type-check the test suites too (tsconfig.app.json covers only src/)
```

### End-to-end (Playwright)

The browser is a separate download and is **not** installed by `npm ci`:

```bash
cd frontend
npx playwright install chromium           # first run only (~150 MB, cached outside the repo)

# The suite expects the app to be running: backend on :8000, vite on :5173.
npm run e2e                               # 29 tests, 6 files, 4 role-scoped projects
npm run e2e -- --project=chromium-homeowner   # one role only
```

PowerShell (Windows):

```powershell
cd frontend
npm ci
npx playwright install chromium           # `--with-deps` is Linux-only; omit it here

$env:E2E_BASE_URL = "http://localhost:5173"
npm run e2e
```

`globalSetup` logs in through the real UI as the seeded demo accounts and saves
one `storageState` per role, so the journey specs start authenticated. That
requires the backend to have been seeded with `SEED_DEMO_ACCOUNTS=true`
(never possible in production — see `docs/security/DEMO_ACCOUNTS.md`).

> **Known blocker (IR-S1-001).** Some sandboxes cannot reach
> `cdn.playwright.dev` (TLS `ECONNRESET`), so the browser cannot be downloaded
> and the suite cannot run locally there. It runs in the CI `e2e` job. See
> `docs/DEPENDENCIES.md` §7.

### Repository-wide audits

```bash
python scripts/audit_docs_links.py        # documentation link / file-reference audit
python scripts/audit_secrets.py           # tracked-file secret & hygiene scan
python scripts/check_links.py             # seller links must answer 200 — needs public internet egress
npx tsx scripts/auditDeadKeys.ts          # every interactive control must do something
npx lighthouse http://localhost:4173/ --view   # >=80 target (npm run preview first) — needs Chrome
```

### Test breakdown

| Suite | Tests |
|---|---:|
| `backend/tests/` (full suite) | **620 collected** — 598 passed, 22 skipped |
| ↳ `test_recommender.py` | 30 (spec floor: ≥28) |
| ↳ `test_security_v2.py` | 26 |
| ↳ `test_feedback_v2.py` | 16 |
| ↳ `test_auth.py` | 13 |
| ↳ `test_projects_quota.py` | 14 (designer quota, Stage 1) |
| ↳ `test_weights_profiles.py` | 13 (weight profiles, Stage 1) |
| ↳ `test_perf_v2.py` | 10 |
| ↳ `test_rate_limit.py` | 2 |
| `frontend/tests/unit/` (Vitest) | **65** across 10 files |
| `frontend/tests/e2e/` (Playwright) | **29** across 6 files — CI only |

## Repository layout

```
backend/
  ai/                embedding_service.py · feature_extractor.py (provider-agnostic)
  app/
    api/routes/      auth · users(GDPR) · quiz+recommend · products · moodboards
                     projects+share · subscriptions+payment · admin
    core/            config · security(JWT/bcrypt/Fernet-KMS) · storage(S3) · redis
    services/        recommender (3-stage) · payment · link_checker · emailer
    models/ db/      SQLAlchemy 2.0 models · pgvector column type
  alembic/           migrations (pgvector extension + HNSW index)
  scripts/           seed_products.py · load_realistic_products.py · evaluate_extraction.py
                     seed_perf_products.py · dev_postgres.py
  tests/             620 collected — test_recommender.py (30) · test_security_v2.py (26)
                     test_feedback_v2.py (16) · test_auth.py (13) · test_projects_quota.py (14)
                     test_weights_profiles.py (13) · test_perf_v2.py (10) · test_rate_limit.py (2)
                     benchmark_50_images.json
  security/          pip-audit-allowlist.yml (expiring, justified CVE acceptances)
frontend/
  src/pages/         quiz · recommendations · moodboards · floorplan · shopping-list
                     upgrade · share · designer/* · admin/*
  src/stores/        authStore · quizStore · moodboardStore (Zustand)
  src/lib/           api (fetch + JWT refresh + CSRF double-submit) · constants (i18n-ready) · types
  tests/unit/        Vitest + Testing Library — 65 tests, 10 files (`npm test`)
  tests/e2e/         Playwright — 29 tests, 6 files (`npm run e2e`): deadKeys · auth-negative
                     auth-smoke · journey-homeowner · journey-designer · journey-admin
datasets/            products_realistic*.json · style_taxonomy · questionnaire · subscription_plans
docs/                RELEASE_BASELINE · RELEASE_CHECKLIST · ROLLBACK_AND_VERSIONING · REPRODUCIBILITY
                     ARCHITECTURE · DESIGN_SYSTEM · DEPLOYMENT · API · WALKTHROUGH
  agent-reports/     per-stage agent reports + evidence directories
scripts/             check_links.py · audit_docs_links.py · audit_secrets.py
                     auditDeadKeys.ts · enable_ci.sh
docker-compose.yml · Caddyfile · .github/workflows/ (CI active) · ci/ (staged workflow mirrors)
```

## Security & compliance

TLS 1.3 (Caddy) · bcrypt password hashing · JWT access 15 min / refresh 7 days with
Redis blacklist rotation · Fernet encryption-at-rest abstraction (documented cloud-KMS
path) · GDPR hard delete (`DELETE /users/me`) · no payment card data (gateway redirect
only) · no secrets in the repo — re-verified at `f97bfad` (244 tracked files,
0 findings, evidence in
`docs/agent-reports/baseline-release-evidence/17-secret-scan.txt`) and re-run at
HEAD on 2026-09-01 (**RESULT: PASS**, 0 findings, 0 forbidden paths).
CI is active (`.github/workflows/ci.yml` — Postgres/pgvector + real-Redis suite,
E2E, Lighthouse, security probes) and the hardcoded-demo-account blocker (B-1) is
closed with boot-time refusal in production. Remaining unverified item:
real-model AI extraction accuracy (needs a provider API key — run
`python scripts/evaluate_extraction.py --real` on a networked host; see
[`docs/RELEASE_BASELINE.md`](docs/RELEASE_BASELINE.md) §7).

## Documentation

**Start here — release governance (baseline `f97bfad`, 2026-08-21):**

- [docs/RELEASE_BASELINE.md](docs/RELEASE_BASELINE.md) — authoritative baseline record: verified vs unverified claims, evidence paths, blockers
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) — pre-release gate checklist
- [docs/ROLLBACK_AND_VERSIONING.md](docs/ROLLBACK_AND_VERSIONING.md) — SemVer/tagging policy, rollback runbook, ownership matrix
- [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md) — can a third party rebuild this from a clean clone?
- [integration-request.md](integration-request.md) — cross-agent change requests raised by this stage

**Product & engineering docs:**

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — ADRs, ERD, recommender design
- [docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md) — tokens, components, a11y
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Docker, Liara, Arvan, EC2, runbook
- [docs/API.md](docs/API.md) — endpoint reference (interactive at `/docs`)
- [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md) — 10-minute demo script

## Realistic datasets (V3)

Docker seeds a 150-row Persian sample catalog with Toman prices, real-world dimensions and product-level Digikala/Torob links. The style quiz, taxonomy and plans read the committed files in `datasets/`; mock AI/hash embeddings remain available offline.

```bash
python datasets/expand_products.py
python backend/scripts/load_realistic_products.py --realistic --expand-to 150 --clear
```

The expanded catalog is demo data derived from 20 curated examples—not a live stock feed. For production replacement fields and required service keys, read [the client dataset request](docs/CLIENT_DATASETS_REQUEST.md) and [deployment guide](docs/DEPLOYMENT.md).
