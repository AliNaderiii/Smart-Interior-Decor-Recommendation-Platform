# Smart Interior Decor Recommendation Platform

AI-powered living-room furnishing recommendations with explainability, editable
moodboards, a 2D floorplan preview, validated shopping lists, a designer (B2B2C)
portal, an admin portal with human-in-the-loop AI feature extraction, and a
Zarinpal-based Pro paywall. **MVP scope: living_room only.**

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 19 · Vite · TypeScript (strict) · Tailwind CSS · Zustand · TanStack Query · react-grid-layout |
| Backend | Python · FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 · python-jose · passlib[bcrypt] |
| Data | PostgreSQL 16 + pgvector (`vector(512)`, HNSW) · Redis |
| AI | CLIP ViT-B/32 embeddings (offline hash fallback) · Gemini / OpenAI vision extraction (provider-agnostic via `.env`) |
| Infra | Docker Compose · Caddy (TLS 1.3) · GitHub Actions CI |

## Quick start (one command)

```bash
cp .env.example .env          # then set SECRET_KEY, FERNET_KEY
docker-compose up --build
```

→ App at `https://localhost` (Caddy, TLS 1.3) · API docs at `https://localhost/docs`.
The backend auto-migrates (Alembic) and seeds 100 products + demo accounts on first boot.

| Role | Email | Password |
|---|---|---|
| Homeowner | demo@smartdecor.dev | Demo1234! |
| Designer | designer@smartdecor.dev | Design123! |
| Admin | admin@smartdecor.dev | Admin123! |

## Local development (no Docker)

```bash
# backend — SQLite + fakeredis fallback works out of the box
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/seed_products.py
uvicorn app.main:app --reload --port 8000

# frontend (separate shell) — dev server proxies /api → :8000
cd frontend
npm install
npm run dev
```

## Tests & acceptance gates

```bash
cd backend
pytest tests/ -v                          # 43 tests: 30/30 recommender (incl. p95<2s) + auth/API
python scripts/evaluate_extraction.py     # 50-image benchmark, >=80% required
python -m ai.embedding_service            # model loads <10s, 512-dim sanity check

cd ../frontend
npm run build                             # tsc strict, 0 errors

python ../scripts/check_links.py          # seller links must answer 200
npx lighthouse http://localhost:4173/ --view   # >=80 target (npm run preview first)
```

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
  scripts/           seed_products.py · evaluate_extraction.py
  tests/             test_recommender.py (30) · test_auth.py (13) · benchmark_50_images.json
frontend/
  src/pages/         quiz · recommendations · moodboards · floorplan · shopping-list
                     upgrade · share · designer/* · admin/*
  src/stores/        authStore · quizStore · moodboardStore (Zustand)
  src/lib/           api (axios + JWT refresh) · constants (i18n-ready) · types
docs/                ARCHITECTURE · DESIGN_SYSTEM · DEPLOYMENT · API · WALKTHROUGH
scripts/             check_links.py
docker-compose.yml · Caddyfile · .github/workflows/ci.yml
```

## Security & compliance

TLS 1.3 (Caddy) · bcrypt password hashing · JWT access 15 min / refresh 7 days with
Redis blacklist rotation · Fernet encryption-at-rest abstraction (documented cloud-KMS
path) · GDPR hard delete (`DELETE /users/me`) · no payment card data (gateway redirect
only) · no secrets in the repo. See `docs/DEPLOYMENT.md` §7 for the full mapping.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — ADRs, ERD, recommender design
- [docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md) — tokens, components, a11y
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Docker, Liara, Arvan, EC2, runbook
- [docs/API.md](docs/API.md) — endpoint reference (interactive at `/docs`)
- [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md) — 10-minute demo script
