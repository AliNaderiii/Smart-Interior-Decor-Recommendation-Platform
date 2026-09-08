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
   `final = 0.25·style + 0.25·color + 0.20·budget + 0.15·material + 0.05·pattern + 0.10·fit`
   (profile `current`, config `2026-09-06.1`; the pre-fit split 0.30/0.30/0.20/0.15/0.05
   is kept as profile `current-v1` — see ADR-012)
   - style: cosine similarity (mapped to [0,1])
   - color: perceptual "redmean" RGB distance (cheap Delta-E approximation),
     best-match average across the user palette
   - budget: 1 at window midpoint, linear falloff to edges
   - material/pattern: Jaccard overlap (neutral 0.5 when either side unknown)
   - fit: physical fit of the product footprint in the quiz room (ADR-012;
     neutral 0.5 when either side has no dimensions)

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
precision (0.5); acceptance ≥ 80 %. Measured 2026-09-02 with
`gemini-3.5-flash-lite` / prompt `p5`: **82.2 % PASS**, rank-1 style 60 %,
material P/R 0.85/0.94 (`docs/reports/extraction_report.json`;
`docs/ai/evaluation-report.md` §3.2–3.3). Because the provider's confidence
proved uninformative on that run (0.95 on 48/50), the review gate also flags
`ambiguous_style` — a multi-style answer confined to the confusable cluster
`modern/scandinavian/minimal` — replayed to 0 unflagged style misses
(`scripts/audit_review_gate.py`).

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

## ADR-012 — Dimensional fit as a sixth score component

**Context.** The quiz has collected `room_width_cm × room_length_cm` since the
floor-planner work and the catalogue carries `width/depth/height_cm` for every
product, yet the ranking never looked at either: a 260 cm sofa scored exactly
the same in a 250 × 300 cm studio as in a 5 × 6 m living room. Every consumer
tool we benchmarked (IKEA Kreativ, Houzz, Wayfair Muse) is criticised for
ignoring room geometry — it is the cheapest differentiator we can ship without
computer vision, and it is *data we already have*.

**Decision.** Add a `fit ∈ [0,1]` component computed by
`recommender.fit_score(category, w, d, h, room_w, room_l) -> (score, reason)`
and give it **10 % of the final score**, funded equally from style and colour
(0.30/0.30 → 0.25/0.25). Budget, material and pattern keep their weights so the
client-facing story ("budget 20 %, material 15 %, pattern 5 %") is unchanged.
Rules are per category and live in `recommender_config.json → fit`, not in code:

| category | rule (footprint ratio `r` = product w·d / room w·l) |
|---|---|
| sofa, chair, coffee_table, storage | 1.0 while `r ≤ ideal`; linear to the floor (0.05) at `max`; **floor immediately** if any side is longer than the room or no 76 cm circulation lane remains along the short wall |
| rug | ramps *up* from `min` → 1.0 at `ideal` (too-small rugs are the classic mistake), then decays to 0.3 at `max` |
| decor (curtains) | height only: 1.0 at ≥ 85 % of an assumed 270 cm ceiling, floor above 105 % (`fit_too_tall`) |
| lighting | neutral 0.5 — a pendant's footprint says nothing about fit |
| anything without dimensions | neutral 0.5, `fit_unknown` — **never penalise missing data** |

The explanation gains two keys: `fit_match` (percentage, like the others) and
`fit_reason` — a stable machine code (`fit_unknown | fit_neutral | fit_ok |
fit_tight | fit_too_big | fit_too_small | fit_too_tall`). The engine never emits
prose for it; both locales translate the code in the frontend, and the card
shows a badge only for the three actionable states.

**Consequences.**
* `config_version` → `2026-09-06.1`; every profile must now carry the `fit`
  key (the validator's exact-key rule). The previous weights survive as
  `current-v1` / `client-ad-v1` with `fit: 0.0`, so an A/B against the old
  ranking is one environment variable (`RECOMMENDER_WEIGHT_PROFILE`).
* Cache fingerprints include the config version (`_cfg`), so upgrading never
  serves a stale 5-component explanation under the new weights.
* The harness (`scripts/evaluate_recommender.py --compare-profiles`) exercises
  a 400 × 500 cm room and diffs profiles by `title|price` rather than UUID, so
  the report shows real reorder/drop deltas between `current` and `current-v1`.
* Quiz payloads without room dimensions degrade gracefully: `fit` is neutral
  for every product, i.e. the ranking is a pure re-scaling of the old one.
* Not done (deliberately): door/window positions, ceiling height from the
  quiz, per-wall placement. Those belong to the floor planner (A1/room photo),
  not to a scalar score.

## ADR-013 — Visual search on the existing embedding space

**Context.** "Find me something that looks like this photo" is the feature
every benchmarked competitor sells (Houzz *Visual Match*, RoomStudioAI *shop
the look*, Wayfair). The platform already had the two expensive halves: a
CLIP-space `style_embedding` on every product with an HNSW index (ADR-003/004)
and an embedding service that accepts images. What was missing was an
endpoint, a page, and an honest answer to the question "what happens when CLIP
is not loaded?" — which is the case in CI, in tests, and on the current demo
host.

**Decision.** `POST /api/v1/search/visual` (multipart photo, optional
`category`, `limit ≤ 24`) served by `app/services/visual_search.py`, with two
retrieval modes selected by the active embedding backend and **reported in
`meta.mode`**:

| mode | when | ranking |
|---|---|---|
| `clip` | `EMBEDDING_BACKEND=clip` and the model loaded | photo → CLIP image tower → cosine against product text embeddings (pgvector `<=>` + HNSW on Postgres, Python cosine on SQLite), blended `0.8·clip + 0.2·palette` because CLIP is weak on exact colour |
| `palette` | hash backend (dev / CI / demo) | median-cut dominant palette of the photo (Pillow, 128 px thumbnail, near-black/white swatches demoted) scored with the recommender's own perceptual `color_score` against each product's catalogued colours |

The hash backend's vectors carry **no** visual semantics, so embedding a
photo there would be theatre; the palette path is a real, explainable search
("things in these colours") and the UI says which mode produced the results.
Both modes return the extracted palette so the user can push it into the
style quiz — the bridge back into the recommender.

**Privacy.** The photo is validated by the same hardened pipeline as admin
uploads (magic bytes, 8 MB / 40 MP bounds, re-encode), processed in memory
and discarded: no storage write, no product row, no cache key. This is
tested (`test_photo_is_never_persisted`). IKEA Kreativ is criticised for
scanning rooms without a consent story; we do not keep the image at all.

**Paywall.** Same shape as `/recommend` (ADR-011): free users get the best
match per category in full and the rest as `locked` teasers, enforced in the
route.

**Consequences.**
* One new setting, `VISUAL_SEARCH_RATE_LIMIT_PER_MINUTE` (10) — the call
  costs an embedding and a vector query and is open to every signed-in user.
* Turning on real CLIP is purely operational (`EMBEDDING_BACKEND=clip` +
  torch/sentence-transformers) — no code path changes, `meta.mode` flips.
* Not done: cropping the query to one object (a room photo embeds the whole
  scene), and re-ranking by the user's saved quiz. Both are natural
  follow-ups once real-model quality is measured (Phase A5).

## ADR-014 — Behavioural event capture, no learning yet

**Context.** `docs/ai/feedback-events.md` designed the event model a learning
stage would need — with the key insight that *impressions are the
denominator* and must be recorded from day one — but nothing captured it.
Every competitor that "learns your taste" (Havenly's 2.4 M-render AI, Wayfair
Muse) is built on exactly this stream; without it any later claim of a
learned recommender would be unfounded.

**Decision.** Build the capture side only, exactly as specified, and put a
guard on the honesty boundary:

* `feedback_events` (migration `0006`): append-only, closed vocabulary
  (`impression, click, like, dislike, unlike, save, share, purchase_click`),
  `position` and `weights_version` on every row, `session_id` for anonymous
  viewers, `sample_rate` per row.
* `POST /events`: batch ≤ 100, **always 202** with `{accepted, dropped}` — a
  bad product id drops that event, a storage failure is logged; analytics can
  never fail a user request. Authenticated *or* anonymous; a forged token is
  still 401. Rate-limited per user/session.
* `GET /admin/events/summary`: per-category funnel; rates are `null` without
  impressions; `learning_ready` restates the spec's ≥ 10 000-event threshold
  so the dashboard cannot imply a model.
* Client: batched tracker with impression de-dup, `keepalive` flush on hide,
  never throws. Emits from `/recommendations` (impressions with `quiz_id` +
  `weights_version`, like/dislike/unlike, save), seller links
  (`purchase_click`) and `/visual-search`.
* GDPR: export section, erasure severs `user_id` (rows have no PII).
* **Guard:** `test_ranking_pipeline_does_not_read_the_event_table` — the
  recommender may not import the table until an ADR replaces this one.

**Consequences.** Data starts accumulating now, correctly attributed to the
config version that produced each list, so the A/B and offline-evaluation
steps in the spec's §3 have something to evaluate. Nothing about ranking
changed. One new setting (`EVENTS_RATE_LIMIT_PER_MINUTE`, 60).

## ADR-015 — Room photo → pre-filled quiz, never a submitted one

**Context.** The five-step quiz is the funnel's biggest leak, and every
benchmarked competitor opens with *"upload a photo of your room"* (Havenly's
AI beta, IKEA Kreativ's scene scanner, Wayfair Decorify) rather than a
questionnaire. The platform already owned every expensive piece: hardened
image upload (Stage 03), a taxonomy-clamped vision extractor with a review
gate (ADR-006), and palette extraction (ADR-013). What was missing was the
glue and — more importantly — an honest contract about what one photo can
and cannot tell us.

**Decision.** `POST /quiz/analyze-room` (`app/services/room_analysis.py`)
returns a *suggestion* shaped exactly like `POST /quiz` input plus a
`confidence_tier`; the client applies it to the quiz store
(`applySuggestion`) and the user still walks every step and presses submit.

* **Two signal sources, kept separate.** *Pixels*: `accent_colors` (hue-binned
  saturated pieces — the yellow armchair that share-weighted median-cut
  swallows into the oak floor) followed by `extract_palette`; deterministic,
  always available, applied as the quiz palette as-is because a room's real
  colours are what `color_score` should match. *Vision*: the configured
  provider with a dedicated **room prompt** (`ROOM_PROMPT`, version `r1`,
  stamped separately from the product benchmark prompt `p5`) through the
  same sanitiser and review gate as product extraction.
* **Tiers decide how much the UI dares to pre-select**, and the *server*
  decides the tier: `confident` (real provider, ≥ 0.80, no review reasons),
  `suggested` (real provider, below the bar or with review reasons — shown
  with a "please review" line), `palette_only` (mock / fallback / provider
  failure — only the pixel palette is applied; **a heuristic provider can
  never pre-select a style for a user**, and the card shows a demo badge
  instead of a confidence figure).
* **Dimensions are not estimated.** A single uncalibrated photo cannot yield
  centimetres honestly, and the fit score (ADR-012) would then rank on
  invented numbers. `meta.dimensions_estimated` is `false` and the UI says
  so.
* **Nothing persisted.** Same stance as ADR-013: analysed in memory, no
  storage write, no row, filename kept out of the audit log; rate-limited
  like an upload (`ROOM_ANALYSIS_RATE_LIMIT_PER_MINUTE`, 10).
* `FeatureExtractor.extract_bytes(data, prompt_kind=…)` is the new, additive
  entry point; `extract(image_url)` and every stamp it produces are
  unchanged (the 50-image benchmark is not disturbed).

**Consequences.** On the demo (mock provider) the feature is honest and
still useful — five real colours land in the quiz in ~100 ms. With a real
key the card pre-selects style and materials too; the next measurement is a
small room-photo benchmark (A5), because the product-photo accuracy (82.2 %)
does not transfer automatically to whole rooms.

## ADR-016 — Catalog-integrity gate: a product must be true before it can be recommended

**Context.** A probe of the live demo on 2026-09-07 returned, for the *rug*
category, a card titled «فرش modern» whose image was a living-room sofa,
whose materials were `metal, leather`, and whose seller link was
`https://www.digikala.com/`. The ranking engine was correct — the *data*
was wrong, and nothing in the pipeline could notice. Three root causes:
`seed_products.py` chose photos by row index (`PHOTO_IDS[i % 20]`)
independent of category and sampled materials from the *style*; the
extractor was never asked what object the picture shows; and
`is_verified` was the only gate, with no rule about what a verified row
must satisfy. For a product that is sold, a wrong recommendation is a
defect, not a demo artefact — so correctness became a first-class,
enforced property of every catalog row.

**Decision.** A pure policy module `ai/catalog_integrity.py`
(`INTEGRITY_POLICY_VERSION`) evaluates a row and returns reason codes in two
tiers:

* **Truth tier — always blocking** (`ALWAYS_BLOCKING`): `image_category_mismatch`
  (the p6 `detected_category` disagrees with the row), `image_unreachable`,
  `material_implausible` (per-category "cannot be" sets — a rug is never
  metal), `dimensions_out_of_band`, `title_fa_invalid` (no Persian letters, or
  an English taxonomy token not introduced by a model marker — «فرش modern» is
  a template leak, «مبل راحتی مدل Modern» is a real listing), `seller_link_dead`,
  `category_unknown`. A row failing this tier is *wrong*, in any environment.
* **Sellability tier — blocking only in production** (`PRODUCTION_BLOCKING`,
  `strict = settings.is_production`): `synthetic_row` (source
  `synthetic-demo`/`perf`, including the curated realistic sample),
  `duplicate_image`, `seller_link_missing`, `seller_link_shallow` (root,
  category or search page), `price_stale` (never confirmed or > 30 days),
  `price_out_of_band`, `title_fa_missing`. These rows are *not inventory*;
  dev, CI and preview deployments may still recommend them (labelled), a
  sold deployment may not.

Enforcement points, all reading the same verdict persisted on the row
(`integrity_ok`, `integrity_reasons`, `integrity_checked_at`; migration
`0007`, plus provenance `source`, `source_product_id`, `image_phash`,
`price_checked_at`):

1. **Writes evaluate.** `POST /products`, `POST /products/upload`,
   `PATCH /products/{id}` and both seed/import scripts stamp the verdict.
2. **Verification refuses.** `POST /products/{id}/verify` (and `PATCH … is_verified`)
   answer **409** with the codes while the truth tier fails; `?force=true`
   overrides, is written to the audit log (`product_verify … FORCED`) and
   leaves an `admin_override` marker on the row.
3. **Runtime excludes.** Stage A of the recommender and the visual-search
   candidate query add `integrity_ok IS NOT FALSE`. `NULL` (legacy rows before
   `scripts/backfill_integrity.py` has run) stays eligible so a deploy never
   goes dark; only an explicit `False` excludes. `meta.catalog_quality`
   reports eligible/excluded per queried category so a thin result is
   explainable, and `RECOMMENDER_CONFIG_VERSION` was bumped because the
   filter semantics changed.
4. **CI gates the data.** `scripts/audit_catalog.py` (exit 1 on any verified
   row failing the enforced tier) runs on the committed sample catalogs and
   on the seeded test database; `--strict` reports what production would
   exclude; `--check-images` HEADs every image on an egress-enabled machine.
5. **Synthetic data is refused in production.** `seed_products.py` exits 0
   without writing when `APP_ENV=production` unless `--allow-synthetic`
   (start commands must not crash-loop); even then the gate excludes the rows.

The vision prompt moved to **`p6`**: one added scalar, `detected_category`
(seven categories + `other`), plumbed through `_sanitize`, the mock provider
(filename keywords), `extraction_raw` and `review_decision(expected_category=…)`
(`category_mismatch`). The scoring fields are unchanged, so the p5 REAL
benchmark remains the accuracy reference until a p6 run is recorded.
`POST /products/upload` now drafts the row in the detected category instead
of a hard-coded `sofa`, and stores a 64-bit dHash (`image_phash`) so two
uploads of the same photo are caught regardless of storage key.

**Consequences.** The seed catalogs were rebuilt to be category-consistent
(per-category photo pools, plausible materials, real Persian nouns, dimension
bands) and the curated sample lost its two cross-category photo reuses and
one dead photo; both pass the truth tier in CI. Under `APP_ENV=production`
the sample catalogs are *excluded by design* — a sold deployment must import a
real seller feed (the P4-ب importer — a follow-up, not part of this ADR), and until then the API serves
an honest empty catalog rather than a plausible-looking wrong one. The SPA
shows provenance on the card (`Demo item` badge for synthetic rows, price
check age for verified rows), the admin table gains an Integrity column with
the reasons in the reviewer's language, and `GET /admin/stats` exposes the
counts. Costs: one extra `GROUP BY` per uncached `/recommend` (sub-ms at the
current catalog size), one 409 round-trip in the review flow, and the p6
benchmark run still owed.

## ADR-017 — The image prepares its own database: a self-bootstrapping entrypoint

**Context.** After ADR-016 merged, the live demo on Render kept answering
`POST /recommend` with 500 and the demo login with 401: the code expected
migration `0007`, the database was at `0005`, and the catalog was the
pre-ADR-016 synthetic set that the gate rightly excludes wholesale. The
documented fix — run `alembic upgrade head`, reseed, backfill — assumed an
operator hook that the hosting plan does not have: no shell, no pre-deploy
command, and a start command the free tier does not let you edit. The only
thing that runs on such a host is the image's `CMD`. A deploy that needs a
human to finish it is not a deploy.

**Decision.** `backend/Dockerfile` runs `python scripts/entrypoint.py`, an
idempotent five-step boot that owes nothing to the platform:

1. `Settings.validate_runtime()` before touching the database.
2. `alembic upgrade head` in-process, under a PostgreSQL advisory lock so
   replicas do not race, followed by an assertion that the database *is* at
   head — the server never starts on a schema it was not written for.
3. Catalog bootstrap selected by `CATALOG_BOOTSTRAP`: `off` (default),
   `if-empty` (load the sample catalog only into an empty table) or
   `replace@<label>` — delete everything and reload, **once per label per
   database**. The label is claimed as a unique row in the new
   `bootstrap_runs` table (migration `0008`) *before* the first delete, so a
   restart, a rollback or a second replica cannot wipe the catalog twice; a
   failed load releases the claim so the next boot retries. Cached
   recommendations (`rec:*`) are flushed after a replacement.
4. Demo accounts through the existing `demo_seed` gate (never in production).
5. The integrity backfill (`price_stale` moves with time; re-evaluating per
   boot is the point).

Then it `exec`s uvicorn with `${PORT}` and `${WEB_CONCURRENCY}` honoured.
Both loading modes are refused under `APP_ENV=production` twice: by
`validate_runtime` (the process does not boot) and by the step itself. The
sample catalog is `source=synthetic-demo`; ADR-016 already excludes it in
production, and a sold deployment imports real inventory.

**Alternatives rejected.** *A start-command override* — unavailable on the
plan, and an out-of-repo command is invisible to review and CI. *An env-var
"clear once" flag with no record* — the operator must remember to remove it
before the next deploy, and forgetting means wiping the catalog on every
boot; a database row remembers on their behalf. *Auto-detecting a purely
synthetic legacy catalog and clearing it* — deleting data because it looks
deletable is the kind of cleverness a data pipeline should not have; the
operator names the replacement, the database records it. *Recording the
marker in `audit_logs`* — that table is pruned on a retention window, and a
once-only marker that expires is not a marker.

**Consequences.** Compose files are untouched (each still sets an explicit
`command:`; production stays migrations + server with the catalog loaded by
the `catalog-bootstrap` profile job), so `tests/test_production_seeding.py`
holds unchanged. The Render deploy becomes dashboard-only: set
`CATALOG_BOOTSTRAP=replace@<date>` once, then `if-empty`. `tests/test_entrypoint.py`
covers the grammar, the once-per-label lock, the failure release, the
production refusal, the image wiring and a subprocess boot on SQLite.
Costs: one extra table, one more boot-time step (~2 s for 150 rows), and a
deploy log that now says what it did.

## Data model (ERD)

```
users 1──1 subscriptions        users 1──* payments (authority/ref only)
users 1──* style_quizzes ──* share_links
users 1──* moodboards (items JSONB: {product_id,x,y,w,h}; shopping_list JSONB)
users(designer) 1──* projects 1──* style_quizzes
products (colors/styles/materials/patterns JSON, style_embedding vector(512),
          is_verified, seller_link_ok, extraction_confidence)
bootstrap_runs (label UNIQUE, action, detail, created_at — ADR-017 once-only record)
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
