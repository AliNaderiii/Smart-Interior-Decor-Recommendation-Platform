# Smart Interior Decor Recommendation Platform

AI-powered living-room furnishing recommendations with explainability, editable
moodboards, a 2D floorplan preview, validated shopping lists, a designer (B2B2C)
portal, an admin portal with human-in-the-loop AI feature extraction, and a
Zarinpal-based Pro paywall. **MVP scope: living_room only.**

> **Release baseline.** This tree was audited at commit `f97bfad` on 2026-08-21.
> Verified-at-HEAD: backend 97/97 tests, frontend strict build, secret scan clean.
> Not verified at HEAD: Postgres+pgvector parity, real-model AI accuracy, seller-link
> liveness, Lighthouse. Read [`docs/RELEASE_BASELINE.md`](docs/RELEASE_BASELINE.md)
> before quoting any number from this repository to a client.

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
On first boot the backend runs `alembic upgrade head` and then
`load_realistic_products.py --realistic --expand-to 150 --if-empty --from-json`,
which loads the **150-row Persian demo catalog**. Demo accounts are enabled
only by the development overlay; the production overlay never enables them.
(`backend/scripts/seed_products.py`, which generates 100 synthetic products, is
the separate no-Docker path documented under *Local development*.)

### Demo accounts — development only

| Role | Email | Password |
|---|---|---|
| Homeowner | demo@smartdecor.dev | Demo1234! |
| Designer | designer@smartdecor.dev | Design123! |
| Admin | admin@smartdecor.dev | Admin123! |

> **Production warning.** These credentials are hardcoded in
> `backend/scripts/seed_products.py` and `backend/scripts/load_realistic_products.py`,
> and the seeder runs unconditionally on container start — including when
> `APP_ENV=production`. A production deployment therefore ships with a known
> admin password unless the accounts are removed or rotated immediately after
> the first boot. Tracked as a release blocker: see
> [`docs/RELEASE_BASELINE.md`](docs/RELEASE_BASELINE.md) §7 (B-1) and
> [`integration-request.md`](integration-request.md) IR-001.

## Dev vs Production data engines — read this

| | Dev / CI | Production |
|---|---|---|
| Database | SQLite fallback (vector column degrades to JSON, cosine in Python) | **PostgreSQL 16 + pgvector required** — fused `<=>` query + HNSW index |
| Embeddings | deterministic 512-dim hash (offline, hermetic tests) | **real CLIP ViT-B/32** — `python scripts/seed_products.py --real-embeddings` once, or `--from-json` after generating the embeddings JSON at **backend/seed_data/embeddings_real.json** on a networked machine (**that file is not in this repository** — four other docs wrongly call it "committed"; see IR-003) |
| Extraction | `AI_PROVIDER=mock` heuristic | `AI_PROVIDER=gemini` (or `openai`) + API key; validate with `python scripts/evaluate_extraction.py --real` |
| Redis | in-process fakeredis (per-worker!) | real Redis (`REDIS_URL`) — shared cache, JWT blacklist and rate limiting |

Postgres parity was demonstrated on **2026-08-19 at commit `a847ad5`**, when the
suite contained 45 tests (`docs/reports/postgres_parity.md`). The suite has since
grown to **97 tests** and that Postgres run has **not** been repeated — the
baseline audit environment has no Docker or PostgreSQL binary. Treat Postgres
parity as *previously evidenced, currently unverified at HEAD*; re-run it before
release:

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml \
  run --rm backend sh -c "alembic upgrade head && pytest tests/ -v"
```

## Local development (no Docker)

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

Counts below were measured at commit `f97bfad` on 2026-08-21 — see
[`docs/RELEASE_BASELINE.md`](docs/RELEASE_BASELINE.md) for the full evidence trail.

```bash
cd backend
pytest tests/ -v                          # 97 passed (see breakdown below)
python scripts/evaluate_extraction.py     # 50-image benchmark, >=80% required — MOCK mode, 100%
python -m ai.embedding_service            # backend=hash dim=512, load+embed <10s sanity check

cd ../frontend
npm run build                             # tsc strict + vite, 0 errors
npm run lint                              # oxlint — 0 errors, 12 warnings at f97bfad

python ../scripts/audit_docs_links.py     # documentation link / file-reference audit
python ../scripts/audit_secrets.py        # tracked-file secret & hygiene scan
python ../scripts/check_links.py          # seller links must answer 200 — needs public internet egress
npx lighthouse http://localhost:4173/ --view   # >=80 target (npm run preview first) — needs Chrome
```

| Test file | Tests |
|---|---:|
| `backend/tests/test_recommender.py` | 30 |
| `backend/tests/test_security_v2.py` | 26 (22 functions, 4 parametrised) |
| `backend/tests/test_feedback_v2.py` | 16 |
| `backend/tests/test_auth.py` | 13 |
| `backend/tests/test_perf_v2.py` | 10 |
| `backend/tests/test_rate_limit.py` | 2 |
| **Total** | **97** |

Measured against the SQLite + fakeredis dev fallback. The frontend has no unit
test runner at this commit; `frontend/tests/e2e/deadKeys.spec.ts` is a Playwright
spec and `package.json` exposes no `test` script — see
[`docs/RELEASE_BASELINE.md`](docs/RELEASE_BASELINE.md) §7 (B-4).

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
  tests/             test_recommender.py (30) · test_security_v2.py (26) · test_feedback_v2.py (16)
                     test_auth.py (13) · test_perf_v2.py (10) · test_rate_limit.py (2)
                     benchmark_50_images.json
frontend/
  src/pages/         quiz · recommendations · moodboards · floorplan · shopping-list
                     upgrade · share · designer/* · admin/*
  src/stores/        authStore · quizStore · moodboardStore (Zustand)
  src/lib/           api (fetch + JWT refresh + CSRF double-submit) · constants (i18n-ready) · types
  tests/e2e/         deadKeys.spec.ts (Playwright; no `npm test` script wired yet)
datasets/            products_realistic*.json · style_taxonomy · questionnaire · subscription_plans
docs/                RELEASE_BASELINE · RELEASE_CHECKLIST · ROLLBACK_AND_VERSIONING · REPRODUCIBILITY
                     ARCHITECTURE · DESIGN_SYSTEM · DEPLOYMENT · API · WALKTHROUGH
  agent-reports/     per-stage agent reports + evidence directories
scripts/             check_links.py · audit_docs_links.py · audit_secrets.py
                     auditDeadKeys.ts · enable_ci.sh
docker-compose.yml · Caddyfile · ci/github-ci.yml (move to .github/workflows/ to enable)
```

## Security & compliance

TLS 1.3 (Caddy) · bcrypt password hashing · JWT access 15 min / refresh 7 days with
Redis blacklist rotation · Fernet encryption-at-rest abstraction (documented cloud-KMS
path) · GDPR hard delete (`DELETE /users/me`) · no payment card data (gateway redirect
only) · no secrets in the repo — re-verified at `f97bfad` by
`python scripts/audit_secrets.py` (244 tracked files, 0 findings, 0 forbidden
paths, evidence in `docs/agent-reports/baseline-release-evidence/17-secret-scan.txt`).
See `docs/DEPLOYMENT.md` §7 for the full mapping and
[`docs/RELEASE_BASELINE.md`](docs/RELEASE_BASELINE.md) §7 for the open blockers
(hardcoded demo accounts, CI not active, unverified real-model AI evidence).

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
