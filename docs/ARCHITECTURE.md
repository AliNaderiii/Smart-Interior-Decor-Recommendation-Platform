# Architecture Decision Record — Smart Interior Decor Recommendation Platform

MVP scope: **living_room only**. Out of scope: 3D/AR/VR, native mobile, real-time seller feeds.

## System overview

```
Browser ──HTTPS/TLS1.3──▶ Caddy ──▶ frontend (nginx, React 19 SPA)
                            │
                            └─/api──▶ backend (FastAPI, 2 workers)
                                        │            │
                                 PostgreSQL 16     Redis 7
                                 + pgvector        (cache + JWT blacklist)
                                        │
                                 S3-compatible storage (Arvan/Liara/AWS)
```

One command: `docker-compose up --build`.

## ADR-001 — Monorepo

`/frontend`, `/backend`, `/docs`, `/scripts`, one `docker-compose.yml`. A 21-day MVP
with one team benefits from atomic cross-stack commits and a single CI pipeline.

## ADR-002 — FastAPI + SQLAlchemy 2.0 (sync)

**Decision:** synchronous SQLAlchemy sessions running in FastAPI's threadpool.

**Why:** the hot path (`/recommend`) is dominated by a single pgvector query +
in-process scoring; async adds session-lifecycle complexity without measurable
gain at MVP traffic. Alembic + sync sessions are also the most battle-tested combo.
The API surface stays `async`-compatible — swapping `Session` for `AsyncSession`
is contained in `app/db/session.py` + route signatures.

## ADR-003 — pgvector `vector(512)` with portable fallback

**Decision:** `vector(512)` matching CLIP ViT-B/32 output. HNSW index with
`vector_cosine_ops` (created in migration `0001`).

`app/db/types.py` degrades to a JSON-encoded TEXT column on SQLite so unit tests
run with zero infrastructure; the recommender then computes cosine similarity in
Python — same math, same results.

## ADR-004 — Embeddings: CLIP with deterministic offline fallback

`ai/embedding_service.py`:
- `EMBEDDING_BACKEND=clip`: `clip-ViT-B-32` via sentence-transformers, loaded once,
  cached in memory. Text and image inputs, L2-normalized.
- `EMBEDDING_BACKEND=hash`: 512-dim feature hashing (unigrams + bigrams, signed
  buckets, L2-normalized). Deterministic, offline, used in CI and as automatic
  fallback when the model can't be downloaded. Cosine geometry over tag-based
  descriptions remains meaningful because similar tag sets share buckets.

The fallback is automatic — CLIP load failure logs a warning and switches backends;
the platform never hard-fails on missing internet.

**Dev vs Prod embeddings — explicit policy (PM P0-2):**
- **CI / offline dev** uses hash embeddings so tests are deterministic and
  hermetic. The 100% benchmark score in CI is a *harness baseline*, not a
  vision-model quality claim.
- **Production** must run real vectors. Two supported paths:
  1. On a networked machine: `python scripts/seed_products.py --real-embeddings`
     — forces CLIP (fails loudly if unavailable), seeds the DB, and exports
     `backend/seed_data/embeddings_real.json` for reuse.
  2. Offline deploys: copy that JSON (generated once on a networked machine) to
     the deploy host, then seed with
     `python scripts/seed_products.py --from-json`. The artefact is
     intentionally **not committed** to the repository (IR-003 — never-commit
     policy for large generated binary-derived assets).
- Real extraction quality: `python scripts/evaluate_extraction.py --real
  [--sample N]` with `AI_PROVIDER=gemini` + `GEMINI_API_KEY` scores the same
  50-image ground truth against the live model and writes
  `docs/reports/extraction_report.json`. If accuracy < 80% the human-in-the-loop
  gate is the safety net: low-confidence extractions stay unverified and never
  enter recommendations.

## ADR-005 — Three-stage hybrid recommender

`backend/app/services/recommender.py`:

1. **Stage A — hard filter (SQL):** `room_type='living_room' AND category=:c AND
   is_verified AND price BETWEEN :lo AND :hi`. Covered by composite index
   `ix_products_filter (room_type, category, is_verified, price_toman)`.
2. **Stage B — semantic retrieval:** on Postgres, fused into the same query:
   `ORDER BY style_embedding <=> :user_embedding LIMIT 100` (HNSW, cosine).
3. **Stage C — weighted scoring with explainability:**
   `final = 0.30·style + 0.30·color + 0.20·budget + 0.15·material + 0.05·pattern`
   - style: cosine similarity (mapped to [0,1])
   - color: perceptual "redmean" RGB distance (cheap Delta-E approximation),
     best-match average across the user palette
   - budget: 1 at window midpoint, linear falloff to edges
   - material/pattern: Jaccard overlap (neutral 0.5 when either side unknown)

Every result carries `explanation` with per-component percentages and a
Havenly-style summary: *"Style Match 92% | Color Match 85% | Budget Fit 90% |
Material: wood (matches your choice)"*.

**Caching:** Redis `rec:{sha256(canonical-quiz-json)}`, TTL 3600 s. Cache failures
never break the request (log + recompute).

**Latency budget:** p95 < 2 s. Measured in `test_30_p95_latency_under_2s`
(100 varied requests): p95 ≈ tens of ms on the seeded catalog.

## ADR-006 — AI feature extraction, provider-agnostic

`ai/feature_extractor.py` — strategy pattern, provider chosen by `AI_PROVIDER`:
`gemini` (gemini-2.0-flash REST), `openai` (gpt-4o-mini vision REST), `mock`
(deterministic heuristic for offline dev/CI). Prompt forces JSON-only; parsing is
hardened against markdown fences; output is clamped to the style/material/pattern
taxonomy. Provider failure falls back to mock with confidence capped at 0.3 so the
admin human-in-the-loop review flags it.

Benchmark: `backend/tests/benchmark_50_images.json` (50 items with ground truth) +
`backend/scripts/evaluate_extraction.py`. Score = style hit (0.5) + material
precision (0.5); acceptance ≥ 80 %.

## ADR-007 — Auth

- JWT HS256, access **15 min**, refresh **7 days**, unique `jti` per token.
- Refresh rotation: each `/auth/refresh` blacklists the used token in Redis for its
  remaining lifetime. `/auth/logout` blacklists the presented refresh token.
- bcrypt via passlib (`$2b$`).
- MVP tokens live in `localStorage` with an axios interceptor doing transparent
  refresh. **Documented path to httpOnly cookies:** move the refresh token into an
  `HttpOnly; Secure; SameSite=Strict` cookie set by `/auth/login`, keep the access
  token in memory only, add CSRF double-submit on state-changing routes. No API
  shape changes required.

## ADR-008 — Encryption at rest (KMS abstraction)

`app/core/security.py::KMSClient` wraps Fernet with the key from `FERNET_KEY`.
The interface (`encrypt`/`decrypt`) is identical to a cloud KMS envelope-encryption
wrapper; migrating to AWS KMS / Arvan Vault means replacing the key source inside
`KMSClient` only. Postgres volumes should additionally use provider disk encryption.

**Key rotation path:** Fernet supports `MultiFernet([new_key, old_key])` —
rotation is: (1) add the new key first in the keyring, (2) run a background
re-encrypt job (`MultiFernet.rotate(token)`) over stored ciphertexts, (3) drop
the old key. With a cloud KMS the same flow becomes "create new key version →
re-wrap data keys → disable old version"; the `KMSClient` facade keeps both
paths behind one interface.

## ADR-009 — Storage abstraction

`app/core/storage.py` — routes never import boto3. `STORAGE_BACKEND=s3` targets any
S3-compatible endpoint (Arvan, Liara, AWS) via `S3_ENDPOINT/S3_BUCKET/S3_ACCESS_KEY/
S3_SECRET_KEY`; `local` serves `/media/*` from disk for dev/CI.

## ADR-010 — Payments

`app/services/payment.py` — `PaymentGateway` strategy: `zarinpal_sandbox` (default),
`zarinpal`, `mock`; Zibal slots behind the same interface. We store only the gateway
`authority` (redirect token) and final `ref_id`. **No card data ever enters the
system** — the user is redirected to the PSP.

## ADR-011 — Paywall enforced server-side

Free users get the full payload for the **top product per category** only; ranks 2-5
are stripped to teaser fields (`id`, `title`, `image_url`, `locked: true`) *in the
API*, not just blurred in the UI. The frontend additionally ships a
`withSubscription` HOC for gated views.

## Data model (ERD)

```
users 1──1 subscriptions        users 1──* payments (authority/ref only)
users 1──* style_quizzes ──* share_links
users 1──* moodboards (items JSONB: {product_id,x,y,w,h}; shopping_list JSONB)
users(designer) 1──* projects 1──* style_quizzes
products (colors/styles/materials/patterns JSON, style_embedding vector(512),
          is_verified, seller_link_ok, extraction_confidence)
```

GDPR: `DELETE /users/me` hard-deletes the user row and every dependent row
(share links, payments, subscription, moodboards, quizzes, projects) in one
transaction.

## Performance & Lighthouse strategy

- Route-level code splitting (`React.lazy`) + Vite `manualChunks`
  (react-grid-layout isolated in its own lazy chunk).
- Images: Unsplash CDN with `fm=webp&q=70`, explicit `width/height` (no CLS),
  `loading="lazy"` except the rank-1 card (`fetchPriority="high"`).
- nginx: gzip + immutable caching for hashed assets.
- DB: composite hard-filter index + HNSW vector index; Redis result cache TTL 1 h.

## i18n / RTL path (documented, post-MVP)

UI is LTR English for MVP. All display strings live in `frontend/src/lib/constants.ts`;
Persian labels (`fa`) already accompany styles/materials/categories, and prices render
as `45,000,000 تومان`. RTL path: Vazirmatn font, `dir="rtl"` on `<html>`, Tailwind
logical properties (`ms-*/me-*`), locale switch in a `useLocale` hook.
