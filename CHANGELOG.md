# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
as interpreted in [`docs/ROLLBACK_AND_VERSIONING.md`](docs/ROLLBACK_AND_VERSIONING.md)
(MAJOR = breaking API/auth/migration contract · MINOR = new endpoint or portal
capability · PATCH = fix, docs, dependency or CI change).

> **On the retroactive sections.** This file was introduced in Stage 1 (T-1.6);
> the checklist item "`CHANGELOG.md` exists" had been open since the baseline
> audit. The `0.1.0`–`0.4.0-rc.1` sections below are reconstructed from the
> repository's own audited records — `docs/RELEASE_BASELINE.md` §2 (commit
> history read via the GitHub API), `docs/ROLLBACK_AND_VERSIONING.md` §2, and
> the per-stage reports under `docs/agent-reports/`. The historical tags are
> ad-hoc milestone names (`v2-phase2-performance`, `v2-final`, …), not SemVer;
> they are **kept as historical markers and not renamed**, and are mapped onto
> SemVer versions here for the first time. Dates are the dates of the
> underlying commits. Where a claim could not be re-verified at the current
> HEAD it is marked as such rather than restated as fact.

## [Unreleased]

### Added — Catalog-integrity gate: a product must be true before it can be recommended (ADR-016, 2026-09-07)

Root cause fixed: a live probe returned, for *rug*, a card titled «فرش modern»
with a **sofa photo**, materials `metal, leather` and a marketplace-root seller
link. The engine was right, the data was wrong, and nothing could see it.

- **`backend/ai/catalog_integrity.py`** (new, `INTEGRITY_POLICY_VERSION
  2026-09-07.1`) — pure two-tier policy. Truth tier, always blocking:
  `image_category_mismatch`, `image_unreachable`, `material_implausible`,
  `dimensions_out_of_band`, `title_fa_invalid`, `seller_link_dead`,
  `category_unknown`. Sellability tier, blocking only in production:
  `synthetic_row`, `duplicate_image`, `seller_link_missing`,
  `seller_link_shallow`, `price_stale` (> 30 d), `price_out_of_band`,
  `title_fa_missing`. Bilingual reason texts.
- **Migration `0007_product_integrity`** — `source`, `source_product_id`,
  `image_phash`, `price_checked_at`, `integrity_ok` (nullable; NULL = legacy,
  still eligible), `integrity_reasons`, `integrity_checked_at`.
- **Enforcement** — `POST/PATCH /products` and `/products/upload` stamp the
  verdict; `POST /products/{id}/verify` (and `PATCH … is_verified`) return
  **409** with the codes while the truth tier fails, `?force=true` overrides
  with an audit record and an `admin_override` marker; recommender Stage A
  (SQLite + pgvector paths) and visual-search candidates add
  `integrity_ok IS NOT FALSE`; `meta.catalog_quality` per queried category;
  `GET /admin/stats` gains `integrity_excluded_products` + `catalog_integrity`.
  `RECOMMENDER_CONFIG_VERSION` → `2026-09-07.1` (weights unchanged; filter
  semantics changed → cache identity changed).
- **Extraction prompt `p6`** — adds the scalar `detected_category` (7 categories
  + `other`); `_sanitize`, mock provider (filename keywords), failed-extraction
  shape and `review_decision(expected_category=…)` → `category_mismatch`.
  `POST /products/upload` drafts the row **in the detected category** (was a
  hard-coded `sofa`) and stores a 64-bit dHash (`image_phash`). Scoring fields
  unchanged; the p5 REAL artefact (82.2 %) remains the reference.
  `AI_STACK_VERSION` → `2026-09-07.2`.
- **Scripts** — `scripts/audit_catalog.py` (CI gate; `--strict`, `--json`,
  `--check-images`, `--file <catalog.json>`; exit 1 on a failing verified row),
  `scripts/backfill_integrity.py` (`--unverify-failing`, `--reset-overrides`,
  `--dry-run`). `seed_products.py` rebuilt: per-category photo pools (curated,
  HTTP-200-checked), materials ⊆ category-plausible set, real Persian titles,
  dimension bands, `source="synthetic-demo"`, and a **production refusal**
  (exit 0, nothing written) unless `--allow-synthetic`.
  `load_realistic_products.py` stamps `source="synthetic-demo"` and
  `detected_category`, and reports what strict mode excludes.
- **Data** — `datasets/products_realistic.json`: the rug that shared the sofa
  photo, the chair that shared the coffee-table photo and the storage row with
  a dead (404) photo now have category-correct, live photos; the 150-row
  expansions regenerated (image URLs only). No photo is shared across
  categories in any committed catalog.
- **CI** — new "Catalog integrity" steps audit the three committed catalogs and
  the seeded test DB (truth tier, blocking) and upload the strict report as an
  artefact. `docker-compose.yml` `catalog-bootstrap` prints the strict audit
  after loading.
- **Frontend** — `ProductCard`: `Demo item` provenance badge for synthetic rows
  and price-check age for verified rows; `RecommendationsPage`: note when the
  gate hid products; admin `ProductsPage`: Integrity column with localised
  reasons and a 409 → confirm → `?force=true` verify flow; `lib/integrity.ts`;
  fa/en strings; 8 new unit tests.
- **Tests** — `backend/tests/test_catalog_integrity.py` (61 tests: policy,
  service, recommender/visual-search exclusion, HTTP verify gate, p6 plumbing,
  seed scripts, audit CLI). Backend 804 passed / 22 skipped on SQLite
  (Python 3.12 / 3.13 / 3.14) and 812 passed / 14 skipped on PostgreSQL 16 +
  pgvector across three consecutive runs on one persistent database; vitest 102.
- **Docs** — ADR-016 in `docs/ARCHITECTURE.md`; `docs/API.md` (products,
  recommend meta, admin stats); `docs/DEPLOYMENT.md` upgrade checklist;
  `docs/ai/model-versions.md`, `docs/ai/evaluation-report.md` (p6 stance);
  risk register **AI-19**.
- **Fixed (found by the smoke run)** — `link_checker.check_product_link`
  raised `StaleDataError` in the background task when the product was deleted
  while its seller-link HEAD was still in flight; the result is now discarded
  with an info log. `seed_perf_products.py` writes the new columns
  (`source='perf'`).
- **Fixed (found by rehearsing the Render upgrade on a replica)** — migration
  `0006_feedback_events` is now idempotent: every seed script calls
  `Base.metadata.create_all`, so a database seeded by newer code *before*
  `alembic upgrade head` ever ran already owns `feedback_events`, and the first
  real migration died with `DuplicateTable` — exactly the state of the live
  demo database (stamped 0005). The migration adopts the existing table and
  advances the stamp.
- **Fixed (Windows dev boxes)** — `requirements.lock.txt` pins `uvloop` with
  `sys_platform != "win32"`; it is a Linux/macOS-only extra of
  `uvicorn[standard]` with no Windows wheel, so the unmarked pin made the whole
  locked install fail on Windows (`docs/DEPENDENCIES.md`).
- **Tightened** — `title_fa_invalid` no longer flags real listings that carry a
  Latin model name («مبل راحتی مدل Modern»): an English taxonomy word is
  invalid only when it is not introduced by a model marker
  (مدل/طرح/سری/کد/برند). The template leak «فرش modern» is still caught.
- **Test hygiene on a persistent database** — the HTTP-created rows of
  `test_catalog_integrity.py` and the twin sofas of `test_fit_score.py` are
  removed/cleared per run; CI PostgreSQL runs pytest more than once per job
  and the leftovers crowded a narrow budget window past `MAX_RESULTS`.

### Changed — AI evaluation report aligned with the REAL benchmark; review gate made structural (2026-09-07)

- **`docs/ai/evaluation-report.md`** — §3.2 no longer says BLOCKED: it
  records the 2026-09-02 REAL run (`gemini-3.5-flash-lite`, prompt `p5`,
  **82.2 % PASS**, 50/50 model-analysed) and a new §3.3 decomposes it from
  the per-item predictions: rank-1 style accuracy **60 %** (the overlap
  style term contributes +8 pts via the second slot), material P/R
  0.85/0.94, ECE 0.368 (0.95 confidence on 48/50), 95 % CI ≈ ±6 pts, and a
  confusion matrix showing every style miss is a two-style hedge inside
  `{modern, scandinavian, minimal}` (rugs 4/6, curtains 3/6 wrong). §1, §2,
  §7, §8, README, RELEASE_CHECKLIST (B-5/BL-3 closed), RELEASE_BASELINE,
  model-versions and risk register (new **AI-19**) follow.
- **`ai/extraction_review.py` — `ambiguous_style` flag.** The confidence
  rule flagged **0/50** real extractions (provider confidence is
  uninformative), so the gate now also pre-flags a multi-style answer
  confined to one confusable cluster (`AMBIGUOUS_STYLE_CLUSTERS`). Replayed
  against the committed artefact: 27 flagged (mean 0.72) / 23 passed (mean
  0.94, **0 unflagged style misses**). A pre-flag for the reviewer, never a
  rejection; single styles and cross-cluster blends are untouched.
  `AI_STACK_VERSION` → `2026-09-07.1`.
- **`scripts/audit_review_gate.py`** (new) — replays the current gate over
  any REAL artefact without an API key and reports what passed unflagged
  and how much of it was wrong; refuses MOCK artefacts.
- **`scripts/evaluate_extraction.py`** — prints/stores `style_rank1_accuracy`
  and `hedge_gain` beside the headline; a MOCK run can no longer overwrite a
  REAL `docs/reports/extraction_report.json` (goes to
  `extraction_report.mock.json`, git-ignored).
- Tests: `tests/test_review_gate_replay.py` (22: rule + replay tripwire),
  `tests/test_evaluate_extraction_harness.py` (8: artefact guard, scoring
  rule). Suite: 743 passed / 22 skipped.

### Added — room photo → pre-filled style quiz (ADR-015, 2026-09-07)

- **`POST /api/v1/quiz/analyze-room`** — one photo of the user's living room
  → a quiz-shaped `suggestion` (styles, materials, colour palette, pattern)
  plus a server-decided `confidence_tier`. Same upload hardening as admin
  uploads, analysed in memory, never stored;
  `ROOM_ANALYSIS_RATE_LIMIT_PER_MINUTE` (10).
- **`app/services/room_analysis.py`** — pixels first: `accent_colors`
  (hue-binned saturated accent pieces that share-weighted median-cut
  swallows) + `extract_palette`; then the configured vision provider with a
  dedicated **room prompt** (`ROOM_PROMPT`, `ROOM_PROMPT_VERSION = "r1"`,
  stamped separately from the product benchmark prompt). Tiers:
  `confident` / `suggested` / `palette_only` — a heuristic (mock) provider
  can never pre-select a style. Room dimensions are explicitly *not*
  estimated (`meta.dimensions_estimated: false`).
- **`FeatureExtractor.extract_bytes(data, prompt_kind=…)`** — additive
  in-memory entry point sharing stamping, fallback and review gate with
  `extract(image_url)`; Gemini/OpenAI/Mock providers gained `extract_bytes`.
- **Quiz page** — `RoomPhotoPrefill` card at the top of step 1: photo →
  `quizStore.applySuggestion` (clamped to the store's limits, replace not
  merge) → every step stays editable; copy follows the tier, demo badge
  instead of a confidence figure when the provider is heuristic. Step-1 hint
  is now localised (was English-only in the Persian UI).
- Tests: `backend/tests/test_room_analysis.py` (27),
  `frontend/tests/unit/roomPhotoPrefill.test.tsx` (8).

### Added — behavioural event capture, honestly scoped (ADR-014, 2026-09-06)

- **`feedback_events` table** (migration `0006`) — the append-only stream
  `docs/ai/feedback-events.md` designed: closed vocabulary (`impression,
  click, like, dislike, unlike, save, share, purchase_click`), `position`,
  `weights_version`, `session_id`, `sample_rate`. No PII, no free text.
- **`POST /api/v1/events`** — batch ≤ 100, **always 202** `{accepted,
  dropped}` (analytics never fails a user request), signed-in or anonymous
  (forged token still 401), `EVENTS_RATE_LIMIT_PER_MINUTE` (60).
- **`GET /api/v1/admin/events/summary`** — per-category funnel with rates
  only where impressions exist and a `learning_ready` flag that restates the
  spec's ≥ 10 000-event threshold. Rendered as an **Engagement funnel** panel
  on `/admin/subscriptions`.
- **Client tracker** `src/lib/events.ts`: batched, impression de-dup per
  session·product·context, `keepalive` flush on tab hide, never throws.
  Emitters on `/recommendations` (impressions with `quiz_id` +
  `weights_version`, like/dislike/unlike, save), seller links
  (`purchase_click`), `/visual-search` (impressions, save).
- **GDPR:** export gains `behavioural_events`; erasure severs `user_id`.
- **Honesty guard:** `test_ranking_pipeline_does_not_read_the_event_table` —
  the recommender is still the bounded thumbs re-rank; nothing learns yet.
- Tests: `tests/test_feedback_events.py` (11), `events.test.ts` (7).

### Added — visual search: find catalogue pieces that look like a photo (ADR-013, 2026-09-06)

- **`POST /api/v1/search/visual`** (`app/api/routes/search.py`,
  `app/services/visual_search.py`): multipart photo + optional `category`
  and `limit ≤ 24`, any signed-in user, `VISUAL_SEARCH_RATE_LIMIT_PER_MINUTE`
  (10). The photo goes through the same hardened validator as admin uploads,
  is processed **in memory only** and never stored, cached or turned into a
  row (tested).
- **Two honest retrieval modes**, reported in `meta.mode`: `clip` (photo →
  CLIP image tower → cosine against product embeddings via pgvector/HNSW,
  blended `0.8·clip + 0.2·palette`) when the real backend is loaded; `palette`
  (median-cut dominant colours scored with the recommender's perceptual
  `color_score`) under the hash backend used in CI/dev/demo. Both return the
  extracted palette; the UI can push it into the style quiz.
- **Paywall** mirrors `/recommend`: free users get the top hit per category
  in full, the rest as `locked` teasers, enforced server-side.
- **Frontend** `/visual-search` (lazy chunk, 3 KB gzip): drag-and-drop with
  local preview and client-side size/type checks, category filter, palette
  swatches → "use these colours in the quiz", similarity badges, add-to-
  moodboard, and an explicit mode notice — a colour-only search never
  pretends to be a vision model. Nav link for homeowners and designers,
  command-palette entry, fa/en strings.
- **Tests:** `tests/test_visual_search.py` (21 — palette extraction, both
  modes with a fake CLIP, auth/415/422/429/paywall/audit/privacy),
  `visualSearchPage.test.tsx` (8).

### Added — dimensional fit as a sixth recommender component (ADR-012, 2026-09-06)

The quiz already asked for the room size and every catalogue row already had
`width/depth/height_cm`; the ranking ignored both. A 260 cm sofa scored the
same in a 2.5 × 3 m studio as in a 5 × 6 m living room.

- **Engine.** `recommender.fit_score()` — per-category footprint rules from
  `recommender_config.json → fit` (seating/tables/storage decay past an ideal
  ratio and floor when a side is longer than the room or no 76 cm walkway
  remains; rugs penalise *too small*; curtains are height-only; lighting and
  anything without dimensions are neutral 0.5). Weighted 10 %, funded equally
  from style and colour: `current` = 0.25/0.25/0.20/0.15/0.05/**0.10**.
  `config_version` and `AI_STACK_VERSION` → `2026-09-06.1`; the previous
  weights survive as `current-v1` / `client-ad-v1` (`fit: 0`) for A/B via
  `RECOMMENDER_WEIGHT_PROFILE`. Cache fingerprints now include the config
  version. `POST /recommend` inline quizzes and `?quiz_id=` both pass room
  dimensions through.
- **API.** `explanation.fit_match` (%) and `explanation.fit_reason` (stable
  code: `fit_unknown|fit_neutral|fit_ok|fit_tight|fit_too_big|fit_too_small|fit_too_tall`).
- **Frontend.** Sixth row "Room fit / تناسب با اتاق" in the match breakdown
  (localised reason + product W × D), and a card-face badge for the three
  actionable states only (won't fit / tight / small); no badge when it fits.
- **Tests & tooling.** `tests/test_fit_score.py` (26 cases incl. "fitting twin
  outranks oversized twin" against the seeded catalogue), fidelity tests
  reconstruct the score from all six components, `productCardFit.test.tsx`
  (7), E2E breakdown assertion extended to the `fit` signal. The weights
  harness now runs a 400 × 500 cm room and diffs profiles by `title|price`
  instead of per-DB UUIDs — the previous `docs/reports/weights_profiles.md`
  reported "0 of 5 kept" for every category because each profile was
  snapshotted on a fresh database with new ids.

### Fixed — CI green again after the bilingual/RTL work (2026-09-05)

`main` had been red for 22 consecutive commits, starting at `459fbf4`
("Persian UI, RTL"). Root cause was one change with three symptoms: the UI
became bilingual with Persian as the default, and the test suites were still
written against the English catalogue.

- **Frontend unit tests (4 failures).** `LoginPage` calls `useT()` and was
  rendered without `<LocaleProvider>`. Added
  `tests/unit/renderWithProviders.tsx` (LocaleProvider + `locale=en` pinned
  before mount) and migrated every component spec to it, so the next
  `useT()` added to a component cannot break CI the same way.
- **Playwright E2E (globalSetup could not find the login form).** Added
  `tests/e2e/locale.ts`: seeds `localStorage["smartdecor.locale"]` through an
  init script on every context globalSetup logs in with, and writes a
  session-less `anonymous.json` storageState for the two anonymous projects.
  `E2E_LOCALE=fa` runs the suite against the Persian UI.
- **`journey-homeowner` › match breakdown.** The i18n pass renamed the signal
  labels ("Style" → "Style fit"). The breakdown now carries locale-independent
  hooks (`data-testid="match-breakdown"`, `data-signal="style|color|budget|material"`)
  and the spec asserts on those. Two strings that were still hardcoded English
  inside the Persian UI (`Match breakdown`, `NN% match — why?`) moved to the
  catalogues as `recommendations.breakdownTitle` / `recommendations.matchWhy`.
- **Dead-key sweep hung for 12 minutes.** `el.getAttribute("href")` was read
  *after* the click; when the click navigated to a page with fewer controls,
  `nth(i)` matched nothing and the auto-wait ran until the test timeout. The
  attribute is now read before the click and `actionTimeout: 30s` is set as a
  global safety net. `E2E_SWEEP_ROUTES` narrows the sweep for local bisecting.
- **Sweep › "command palette opens with Cmd+K" was a hydration race.** The
  test pressed Cmd+K right after `domcontentloaded`, but the shortcut listener
  is attached in `CommandPaletteProvider`'s effect ~25 ms later, so the key
  press was lost on a fast machine (3/3 local failures). The spec now waits for
  a React-rendered element (the header's palette button) before pressing.
- **Backend lint.** Unsorted import in `app/models/project.py` (I001) — the one
  line that was failing the backend job and skipping six dependent jobs.
- **Lighthouse › home/mobile LCP gate (3000 ms).** The first green-everything
  run of this branch (34025147386) failed only here: 3008/3009 ms, 8 ms over,
  with *render delay* — not download — as the dominant phase. The 2026-09-04
  landing redesign (scroll-driven depth, gallery, pricing) had grown the entry
  chunk to 423 KB while the hero was still discovered only after React
  rendered. Three changes, each measured with the CI matrix script locally
  (home/mobile median LCP 4565 → 3806 ms simulated in a 2-CPU sandbox; the
  same script on the identical build in CI conditions: 2959 → 2536 ms):
  1. `index.html` preloads the hero with `imagesrcset`/`imagesizes` and
     `fetchpriority="high"` — Vite rewrites the hrefs to the hashed URLs the
     component imports, so the hero request now starts at ~16 ms instead of
     ~150 ms (after the entry chunk executed).
  2. Two phone-sized derivatives (`hero-768.webp` 50 KB, `hero-1080.webp`
     83 KB) via a new `srcSet` prop on `OptimizedImage`; a 412 px viewport
     fetched 145 KB and now fetches 51 KB.
  3. `LoginPage` is route-lazy like `RegisterPage`; it was the only eager
     importer of zod + react-hook-form (entry chunk 423 → 330 KB raw,
     135 → 107 KB gzip).

- **i18n › recommendations page.** Six strings were still hardcoded English
  inside the Persian UI — the header actions (`Upgrade to Pro`,
  `Create moodboard (N)`), the layout toggle (`Grid` / `Masonry`), the
  per-category `N options` counter and the Pro-locked card overlay
  (`N more matches in this room`, `Unlock with Pro`). All moved to the
  catalogues under `recommendations.*`; the English rendering is unchanged.
- **Floorplan in the Persian UI.** The SVG inherited `direction: rtl` from
  the document, which flipped `text-anchor` semantics and pushed the y-axis
  ruler ticks (100…500, "cm") outside the viewBox — they rendered clipped.
  The plan is now `direction="ltr"` (a metric drawing reads the same in any
  language); the `door 80` / `win 140` labels and the footprint caption moved
  to the catalogues (`floorplan.doorLabel/windowLabel/footprint`), and the
  door label sits under the swing arc instead of colliding with the top ruler.

### Added

- **`backend/tests/test_designer_workflow.py` (30 tests).** Migration 0005
  shipped `PATCH /projects/{id}/status`, `POST /share/{token}/approve` (an
  **unauthenticated write**) and `GET /share/{token}/approvals` with no tests.
  Covers ownership (IDOR → 404, homeowner → 403, anonymous → 401), status
  validation, audit trail, upsert idempotency, comment sanitisation and
  length, unknown/oversized token, expiry (410) on all three token endpoints,
  per-IP rate limiting and cross-link isolation.
- **`frontend/tests/unit/sharePage.test.tsx` (6 tests).** The client-side
  approval loop: POST payload, `aria-pressed` reflection, saved verdicts on
  reload, note round-trip, 404/410 error state with no controls, and the
  `javascript:` seller-link guard (X-01). Verified to fail when the sanitiser
  or the payload is broken.

### Fixed — designer workflow (found while writing the tests above)

- `GET /share/{token}/approvals` did not check link expiry, so an expired link
  still disclosed the client's verdicts to anyone holding the URL. All three
  token endpoints now resolve the link through one helper
  (`_load_live_share_link`: 404 unknown, 410 expired).
- `PATCH /projects/{id}/status` was audited as `share_create`. It now records
  its own `project_status` action with the `old->new` transition.

### Changed

- Build-process artefacts (`agent-master-prompts/`, `*MASTER_PROMPT*.md`,
  `PHASE0_AUDIT_GUIDE.md`, `integration-request.md`) moved from the repository
  root to `docs/internal/` (`git mv`, history preserved; see
  `docs/internal/README.md`). `scripts/audit_docs_links.py` and every
  in-repo link updated; docs-link audit and secret scan both PASS.
- README test counts re-measured at HEAD: backend 628 passed / 22 skipped
  (650 collected), frontend 64 unit tests / 11 files, E2E 30 tests.

- **Vercel demo rewrite (`frontend/vercel.json`).** The frontend calls the
  API on the relative path `/api/v1`; for the free demo deploy (Vercel +
  Render) a rewrite proxies `/api/:path*` to the Render backend, so no
  CORS/env wiring is needed in the static build. Replace
  `__RENDER_BACKEND_URL__` with the Render service hostname.

### Fixed

- **UTF-8 evidence artefact on Windows.** `evaluate_extraction.py` wrote
  `docs/reports/extraction_report.json` with the platform default encoding
  (cp1252 on Windows), which makes the committed benchmark evidence fail to
  parse under UTF-8 (Linux/CI). Reads/writes now pin `encoding="utf-8"`;
  the committed PASS report (82.2%, gemini-3.5-flash-lite, prompt p5) was
  re-encoded without touching any value.

- **Gemini resilience + pacing for the offline real benchmark.** The first
  real 50-image run attempts (free-tier Gemini key over a VPN tunnel) died
  to a mix of `429 Too Many Requests` (per-minute quota) and transport
  resets (SSL EOF, `WinError 10053/10061`), each previously degrading that
  image to the labelled mock fallback and therefore invalidating the whole
  run under the real-run guard. `GeminiProvider.extract` now retries
  transient failures — 429, 5xx and `httpx.TransportError` — with
  exponential backoff honouring the server's `Retry-After` header
  (attempt budget via env `GEMINI_MAX_ATTEMPTS`, default 5); 4xx other
  than 429 still fail fast as configuration errors.
  `evaluate_extraction.py` additionally accepts `--sleep SECONDS` to pace
  calls under a per-minute quota and prints the pacing/retry policy in the
  report header.

### Added

- **OpenAI-compatible gateways + local images for `OpenAIProvider`.**
  `OPENAI_BASE_URL` (env) now overrides the default
  `https://api.openai.com/v1`, so any Chat Completions-compatible gateway
  can serve the vision calls (regional aggregators included) with the same
  Bearer-auth contract. Local files passed via the benchmark's
  `--images-dir` are read and inlined as `data:` URLs instead of being
  rejected by URL validation. The provider applies the same transient
  retry/backoff policy as Gemini (429 / 5xx / transport resets,
  `OPENAI_MAX_ATTEMPTS`, default 5).

### Changed

- **Extraction prompt p5: up-to-3 style hedge, co-dominance wording, typed
  arrays.** The p4 full-50 real runs (valid evidence, no fallbacks) landed
  at 79.2% (`gemini-3.5-flash-lite`) — 0.8 points under contract — with
  14/50 style misses at the 2-slot hedge and phantom minority materials
  (a fabric sofa's "wood legs"). p5 allows up to 3 listed styles (free
  under the contract's overlap-based style term; review-gated downstream),
  reframes material as "structurally dominant, co-dominance test, never
  more than 2", and states that every classification field is a JSON
  array. Also hardened `_sanitize`: scalar values where a list was asked
  (e.g. `"patterns": "geometric"`, observed live) are wrapped into a
  one-item list instead of being shredded into single characters.
- **Extraction prompt p4: synonym translation map + 1-2 style hedge.** The
  first p3 real sample (`gemini-3.5-flash`, 5 images) confirmed the
  material fix (micro F1 0.65 → 0.92) but exposed that the model can still
  emit off-list style words ("contemporary"-class synonyms) that
  `_sanitize` then drops — style recall fell to 0.2 and every affected
  item hit the review queue (3/5). p4 embeds an explicit translation map
  (minimalist→minimal, scandi/nordic→scandinavian, contemporary/mid-century
  →modern, traditional→classic, rustic/eclectic/coastal→boho, loft/urban→
  industrial) and allows 1-2 listed styles (best first) — free under the
  contract's overlap-based style term. `evaluate_extraction.py` now also
  embeds per-item predictions (`items[].predicted_*` +
  `unknown_taxonomy_values`) in the report so prompt tuning reads evidence
  straight from the artefact.
- **Extraction prompt p3: strict vocabulary + cardinality lock.** The first
  valid real benchmark run (50 local photos, `qwen3.6-35b` via an
  OpenAI-compatible gateway, prompt p2) measured **70.7%** mean accuracy —
  usable but below the ≥80% contract. The failure signature was
  diagnostic-precision collapse, not mis-seeing: style micro recall 0.72
  (models emit off-list synonyms like "contemporary"/"mid-century" that
  `_sanitize` clamps to nothing) and material micro precision 0.645 with
  recall 0.958 (the p2 wording "pick all that apply" invited over-listing,
  and the benchmark scores material as precision-only). p3 therefore
  demands exactly one listed style (nearest canonical mapping, never a
  synonym), only the 1-2 clearly visible/dominant materials, exactly one
  dominant pattern, and an honest confidence. Bumped
  `EXTRACTION_PROMPT_VERSION` per the versioning rules.
- **README re-synced to the actual HEAD (2026-09-01 re-verification).** Test
  counts updated to freshly measured values (backend 620 collected —
  598 passed / 22 skipped; frontend 65 unit tests across 10 files;
  `test_projects_quota.py` 13 → 14); the quick-start paragraph no longer
  claims the backend seeds the catalog on every boot (Stage-04 removed that
  path — production boot is migrations-only, catalog loading is the explicit
  `catalog-bootstrap` profile job); the stale B-1 "production warning" is
  replaced by a description of the enforced protection (boot-time refusal in
  production); the layout/security sections now state CI is active
  (`.github/workflows/`) instead of "move to enable"; Node ≥ 22 documented as
  a frontend prerequisite (with `.nvmrc`).
- **IR-003 closed.** The two remaining references that implied
  `backend/seed_data/embeddings_real.json` is committed
  (`docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`) now state the artefact is
  generated on a networked machine and intentionally not committed.
- **`ci/github-ci.yml` synced from the active workflow** (it had drifted
  behind `.github/workflows/ci.yml` — actions versions and the Stage-1
  locked-install verification step were missing from the canonical copy).
- **`docs/RELEASE_CHECKLIST.md`: four previously open items ticked with CI
  evidence at HEAD** — Postgres 16 + pgvector suite, real-Redis suite,
  three-role E2E executed green, and the migration downgrade round-trip (B-7) —
  all backed by run
  [#33430375507](https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform/actions/runs/33430375507)
  (2026-08-31, all jobs green); README test-count parity tick re-measured
  locally on 2026-09-01.

### Fixed

- **BUG-401 (hotfix): env-file inline-comment poisoning of demo passwords.**
  `.env.example` carried value-side inline comments (e.g.
  `DEMO_ACCOUNT_PASSWORD=  # [OPTIONAL] test-only override`). Docker Compose's
  `env_file` does not strip inline `#` comments from values, so the comment
  string became the literal `DEMO_ACCOUNT_PASSWORD` and all three demo accounts
  were seeded with it (login with that exact string returned `success:true`).
  Three layers of fix: (a) `.env.example` now keeps every comment on its own
  dedicated line — no value-side inline comment anywhere in the file;
  (b) `scripts/run_local_demo.ps1` strips value-side comments when it generates
  `.env` from the template (defense-in-depth, BOM/line-endings preserved);
  (c) `backend/app/core/demo_seed.py::_password_for()` treats a
  `DEMO_ACCOUNT_PASSWORD` whose stripped value begins with `#` as unset, logs
  loudly, and falls back to the documented dev default. Pinned by regression
  tests (`backend/tests/test_env_template.py`, `test_demo_seeding.py`).

- **Frontend toolchain pin: Node ≥ 22.** `npm test` crashed on Node 20 with
  `TypeError: webidl.util.markAsUncloneable is not a function` (locked
  jsdom/undici stack), while CI silently used Node 22 — a fresh clone on a
  Node-20 machine could not run the unit suites at all. `package.json` now
  declares `engines.node >=22` / `engines.npm >=10` (lockfile synced) and the
  repo ships `.nvmrc` (`22`); README documents the prerequisite.
- **Deprecated Starlette status-code constants replaced** —
  `HTTP_413_REQUEST_ENTITY_TOO_LARGE` → `HTTP_413_CONTENT_TOO_LARGE`
  (4 sites in `backend/app/core/uploads.py`) and
  `HTTP_422_UNPROCESSABLE_ENTITY` → `HTTP_422_UNPROCESSABLE_CONTENT`
  (1 site in `backend/app/api/routes/quiz.py`, 2 in
  `backend/app/core/uploads.py`). Behaviour is identical (same status codes);
  the noisy `StarletteDeprecationWarning` stream in test/server output is
  gone and the code is safe against the constants' future removal.
- **Vite/Vitest native-config warning removed** — `__dirname` does not exist
  in ESM configs once Vite switches to `configLoader: 'native'`; both
  `vite.config.ts` and `vitest.config.ts` now use `import.meta.dirname`
  (valid under the pinned Node ≥ 22 toolchain).
- **Penetration-test telemetry no longer mutates a tracked evidence file.**
  `tests/test_stage3_penetration.py` appended its attack session log to the
  tracked `docs/agent-reports/stage3-evidence/t-3.1-attacks/attack_session.jsonl`
  on *every* run — silently dirtying the working tree, rewriting Stage-3
  historical evidence, and breaking the release-gate invariant "working tree
  clean before the release commit". The log now goes to a per-run temp
  location by default; writing into the tracked evidence directory is an
  explicit opt-in (`PENTEST_EVIDENCE=repo`) for deliberate evidence passes.

- **B-5 enforced: a degraded REAL extraction run can no longer print PASS.**
  When image fetching failed in REAL mode (e.g. the synthetic
  `images.smartdecor.dev` fixture URLs without `--images-dir`), every item
  silently degraded to the filename-keyword fallback (`provider="mock-fallback"`),
  and — because the ground truth is encoded in those slugs — the run printed a
  fabricated **100 % “PASS”**. `scripts/evaluate_extraction.py` now declares any
  REAL-mode run in which a non-real provider label (`failed` / `mock-fallback` /
  `mock` / `exception`) appears as **“INVALID REAL RUN”** (exit 2) with an
  explicit remedy, instead of a quotable result. Verified: forced-failure run
  exits 2 with the loud message; MOCK baseline still exits 0.

- **`--images-dir` now actually feeds local pixels to the vision provider.**
  `_fetch_image_bytes()` accepted only absolute http(s) URLs, so the documented
  real-benchmark path (local photos for the synthetic `images.smartdecor.dev`
  fixture) always failed with “must be an absolute http(s) URL” and silently
  fell back. Existing local paths are now read from disk (size-capped, MIME by
  extension); remote URLs keep the full per-hop SSRF guard. The Gemini request
  shape (base64 `inline_data`) is unchanged.
- **Benchmark v1.1: ground-truth materials re-labelled to real reference
  photographs.** The synthetic slugs encoded implausible combinations
  (e.g. leather and glass *rugs*), which would unfairly penalise a correct
  vision model. Each item’s `material` list now matches the visible materials
  of the paired real photo (`tests/benchmark_50_images.json`; the photo set is
  distributed out-of-tree as `benchmark-images.zip`, not committed). Styles and
  categories are unchanged; MOCK harness re-run stays at 100% (slugs carry the
  same keywords as the corrected ground truth).
- **`scripts/enable_ci.sh` can no longer regress an evolved workflow.** The
  script blindly copied `ci/github-ci.yml` over `.github/workflows/ci.yml`;
  after direct workflow edits (Stage 1 onwards) the staged copy had become
  *older* than the active one, so running the script would have silently
  downgraded CI. It now refuses when the two files differ and offers
  `--sync-canonical` to adopt the active copy instead.

## [0.7.0] — 2026-08-28 (Stage 3: Security Penetration Testing & Compliance Hardening)

Tagged on the merge commit of the Stage-3 PR (#17); see
`docs/agent-reports/stage3-report.md` for executive summary and full technical register.

### Added

- **Automated Security Penetration Test Suite** (`backend/tests/test_stage3_penetration.py`):
  15 test scenarios spanning 14 attack classes (auth brute force & lockout, JWT signature tampering & algorithm confusion, refresh token replay & rotation races, cross-tenant IDOR on moodboards and projects, share-token entropy and PII leakage, RBAC elevation & admin self-demotion, payment verification replay attacks, malicious file upload filtering, SSRF IP-blocklist validation, stored XSS sanitization, CSRF double-submit token enforcement, rate limiting, and information leakage prevention).
- **Compliance Pack & PII Data Map** (`docs/reports/COMPLIANCE_PACK.md`):
  Comprehensive regulatory and security compliance pack covering GDPR Art. 15 (Right of Access / JSON export) and Art. 17 (Right to Erasure / hard deletion), comprehensive PII data map across all DB entities and caches, TLS 1.3 / HSTS / cookie security posture, no-card-data attestation, and client decisions register (C-01 to C-03).
- **Disaster Recovery & Backup Automation** (`scripts/backup_db.sh`, `scripts/restore_db.sh`, `docs/DR_DRILL.md`, `backend/tests/test_dr_restore.py`):
  Standardized PostgreSQL schema + data dump and restore tooling with automated snapshot verification tests.
- **Accessible Modal Primitive `useDialog`** (`frontend/src/hooks/useDialog.ts`):
  Implements document-level `Escape` key handling, keyboard focus trapping (`Tab` / `Shift+Tab`), focus restoration on unmount, and body scroll lock (resolves IR-S1-011).
- **Seller-Link Quarantine Admin Workflow** (`frontend/src/pages/admin/ProductsPage.tsx`, `docs/OPERATOR_SELLER_LINKS.fa.md`):
  Database persistence for `link_status` and `link_checked_at` (Alembic migration `0004_product_link_status.py`), API status filter, UI quarantine badges (`🔴 قرنطینه`, `⚠️ ریدایرکت`, `✓ سالم`), and a Persian operator replacement guide (resolves IR-S2-001).

### Changed

- **Dead-Key Sweep CI Gate** (`ci/ci.stage3.yml`):
  Removed `continue-on-error: true` from the `chromium-sweep` Playwright job, restoring it to a **BLOCKING** check in CI (resolves IR-S1-013).
- Replaced 8 dead/NXDOMAIN URLs in `datasets/products_realistic.json` with live Digikala seller links.
- Migrated all modal surfaces (`DashboardPage.tsx`, `ShortcutsDialog.tsx`, `PresentMode.tsx`, `ProductsPage.tsx`, `CommandPaletteOverlay.tsx`) to `useDialog`.

### Fixed

- **S3-F001 (High · IDOR in `POST /api/v1/quiz`):** `create_quiz` now verifies that the authenticated designer owns the referenced `project_id`, returning HTTP 404 on ownership mismatch.
- **S3-F002 (Medium · GDPR Art. 17 Redis Invalidation):** `DELETE /api/v1/users/me` now flushes user recommendation and export cache keys (`rec:{uid}:*`, `export:{uid}`) from Redis upon account erasure.

---

### Fixed

- **Quota guard reported success for rows it never inserted (production
  driver only).** `insert_project_guarded` returned `bool(result.rowcount)`.
  The DBAPI permits `rowcount == -1` for "unknown", and **psycopg3** — the
  driver CI and production use (`postgresql+psycopg`) — returns -1 for this
  `INSERT ... SELECT`, while psycopg2 returns 0. Since `bool(-1)` is `True`, a
  quota-blocked insert was read as a success and the caller handed the
  designer a project that had never been written. The guard now compares
  explicitly and verifies against the database when the driver cannot report a
  count. Pinned by a driver-independent regression test.
- **Backend suite is idempotent on a persistent database.** The CI backend job
  runs pytest more than once against the same PostgreSQL database; the seeded
  demo designer accumulated projects across runs and, once past the Stage-1
  quota of 2, unrelated tests failed with 402. The session fixture now clears
  rows owned by the `@smartdecor.dev` demo accounts.
- Pytest failures are emitted as GitHub Actions annotations, so a red job is
  diagnosable without downloading logs.

- **Designer quota guard is now atomic on PostgreSQL, not just SQLite.**
  `insert_project_guarded` took no row lock of its own: it relied on the
  caller. Under PostgreSQL's READ COMMITTED isolation every statement takes a
  fresh snapshot, so concurrent transactions all read the pre-insert count and
  all inserted — measured at **5 and 6 rows against a quota of 2**. The
  `SELECT ... FOR UPDATE` now lives *inside* the guard, so any caller gets the
  full guarantee. The production path (`create_designer_project`) was never
  affected: it locked first. Verified against real PostgreSQL 16.2 with a
  negative control (10/10 fail without the lock, 10/10 pass with it).
- **Recommender no longer emits PostgreSQL-only SQL to a SQLite session.**
  `recommend()` branched on the global `settings.is_postgres`, but the
  evaluation harness builds an in-memory SQLite catalog for reproducibility.
  With the process configured for PostgreSQL — as in CI — it sent
  `SET LOCAL hnsw.ef_search` to SQLite (`near "SET": syntax error`), failing
  both weight-profile harness tests. The branch now inspects the session's own
  dialect.
- Both race tests now open their connections *before* the barrier releases the
  workers; without that the threads staggered and the missing lock was caught
  in only 1 run out of 8.

---

## [0.5.0] — unreleased (Stage 1: spec completion & test infrastructure)

Tagged on the merge commit of the Stage-1 PR; see
`docs/agent-reports/stage1-report.md` for the exact annotated-tag commands.

MINOR rather than PATCH: designer project quota enforcement changes the
observable behaviour of `POST /projects` (it can now return 402), and the
recommender gains a configurable scoring-profile capability.

### Added

- **Designer project quota** enforced from the versioned subscription-plan
  dataset (`designer_free` = 2, `designer_studio` = 20, `designer_agency` =
  unlimited). `POST /projects` returns **402** with a Persian, actionable
  message once the plan's quota is used up. Race-safe by construction: a row
  lock plus an atomic `INSERT … SELECT … WHERE (SELECT count) < quota`, so two
  concurrent requests cannot both slip past the limit. Unknown or missing plan
  data fails **closed** (`DESIGNER_PROJECT_QUOTA_FALLBACK`, default 1).
  (`backend/app/services/designer_quota.py`)
- **Switchable recommender weight profiles** (`backend/ai/recommender_config.json`
  v2026-08-26.1) selected by `RECOMMENDER_WEIGHT_PROFILE`:
  - `current` (default) — the ADR-005 baseline: style .30 / colour .30 /
    budget .20 / material .15 / pattern .05
  - `client-ad` — the client advertisement's weights, normalised: the
    as-written set sums to **105 %**, which the validator refuses; the 5-point
    excess is absorbed by `material` (.15 → .10). **Which signal absorbs it is
    an open client decision (C-6).**

  An unknown profile name refuses to boot rather than silently ranking with the
  wrong weights. The active profile is part of the recommendation cache key and
  is stamped into every response's `meta`.
- **Profile comparison harness** — `evaluate_recommender.py --compare-profiles`
  runs all 18 scenarios under both profiles and generates
  `docs/reports/weights_profiles.md` with per-category rank deltas: the C-6
  decision input.
- **Frontend unit test suite** — Vitest + Testing Library, 58 tests across 8
  files (safeUrl, projectStatus, quizStore, authStore, useFeedback, RequireAuth,
  LoginPage, designer quota toast). `npm test` is now a real script and CI runs it.
- **Playwright E2E suite** — 29 specs across 6 files in four role-scoped
  projects (anonymous, homeowner, designer, admin), with sessions minted by a
  real UI login in `globalSetup`:
  - `auth-negative.spec.ts` — XSS payload in the login form, wrong password,
    anonymous access to an admin route
  - `auth-smoke.spec.ts` — a cookie-mode session is actually usable
  - `journey-homeowner.spec.ts` — 5-step quiz → 3–5 ranked items per category
    with explanation chips → moodboard → shopping list with a live total → logout
  - `journey-designer.spec.ts` — dashboard → create to the quota → the 402
    quota wall is visible in the UI
  - `journey-admin.spec.ts` — upload → AI extraction preview → human review →
    approve → verified list → users and subscriptions
  - a new CI `e2e` job runs them against Postgres + pgvector and Redis and
    uploads the JSON/HTML report.
- **Dependency governance** (T-1.5):
  - `scripts/verify_lock_install.py` — proves the resolved environment matches
    `requirements.lock.txt` and publishes the `pip freeze` diff as a CI artifact.
  - `scripts/audit_dependencies.py` — audits the **locked** set and reconciles
    findings against `security/pip-audit-allowlist.yml`, where every acceptance
    needs an owner, a justification and a **mandatory expiry** (max 180 days).
    Expired, malformed or stale entries fail the build.
  - `docs/DEPENDENCIES.md` — lock-refresh policy, ownership, audit cadence and
    Playwright browser installation (incl. Windows/PowerShell).
- `CHANGELOG.md` (this file).

### Changed

- Every CI Python install now resolves `requirements.lock.txt`. The
  **Lighthouse job was the last one still installing the ranges** in
  `requirements.txt`, so it could measure a dependency set no other job and no
  deployment ever used.
- The backend `Dependency audit` step now audits the lockfile instead of
  `requirements.txt` — auditing a file of ranges audits whatever resolves at
  audit time, not what ships.
- The CI frontend `Typecheck` step additionally runs `tsc -p tsconfig.tests.json`,
  so the test suites are type-checked under the same strict flags as `src`
  (`tsconfig.app.json` includes only `src`).
- The CI `e2e` job now seeds products and demo accounts, which the homeowner and
  admin journeys require, and uploads its report on success as well as failure.
- `docs/RELEASE_CHECKLIST.md` re-audited at this HEAD; every tick now links the
  evidence file that backs it.

### Fixed

- **P0 — every authenticated route was unreachable in the default
  configuration.** `RequireAuth` demanded a JWT in `localStorage`, but
  `USE_COOKIE_AUTH=true` (the default) deliberately keeps tokens in httpOnly
  cookies, so a perfectly valid session was bounced to `/login` on every
  auth-gated route. Now accepts a cookie-mode session.
  (`frontend/src/components/guards.tsx`)
- **P1 — login errors were never shown.** The catch block read an
  axios-shaped `err.response.data.error` that this fetch-based client never
  produces, so every failure displayed the generic "Login failed" instead of
  the server's reason. (`frontend/src/pages/LoginPage.tsx`)
- **Designer quota message was swallowed.** The projects dashboard replaced the
  402 body with a generic English toast, so a designer who hit the free limit
  was told nothing about why or what to do. The server's Persian message is now
  surfaced. (`frontend/src/pages/designer/DashboardPage.tsx`)
- `setuptools` pinned at `66.1.1` in the lockfile (a `pip freeze` artefact of
  the build venv) carried PYSEC-2025-49, PYSEC-2026-1918 and PYSEC-2026-3447.
  Raised to `84.0.0`; the audit allowlist is empty.
- A JWT captured verbatim in a Stage-1 evidence log was redacted; the secret
  scan is clean again.

### Security

- Designer quota is enforced server-side and fails closed on bad plan data.
- The dependency audit gate now covers what actually ships, and time-boxes any
  accepted risk.

### Known limitations

- **Playwright browsers cannot be downloaded in the development sandbox**
  (`cdn.playwright.dev` → TLS `ECONNRESET`; blocker **IR-S1-001**). The E2E
  specs therefore run in CI only. Their backend contracts are additionally
  verified locally at the protocol layer (45/45 checks) —
  `docs/agent-reports/stage1-evidence/t-1.4b/`.
- Stage-2/5 acceptance evidence (Lighthouse ≥ 80, LCP < 3 s, real-model AI
  extraction ≥ 80 %, seller-link liveness) remains outstanding and blocked on
  environment/client input, not on code.
- **C-6 (open client decision):** which weight absorbs the advertisement's
  5-point excess. Currently `material`.

---

## [0.4.0-rc.1] — 2026-08-22

Tag: `v0.4.0-rc.1` on `91cc6fe` (merge of PR #13, Stage 04 production
remediation). The first SemVer tag in the repository.

### Added

- Production infrastructure and CI/CD: multi-job GitHub Actions workflow
  (backend vs Postgres 16 + pgvector and Redis, multi-worker verification,
  frontend gates, security scans, Docker build, Lighthouse), health and
  readiness endpoints, observability smoke checks.
  (`docs/agent-reports/infra-report.md`)
- `backend/requirements.lock.txt` — the first pinned resolution of the backend
  dependency set (IR-009).
- Disaster-recovery and rollback documentation.

### Fixed

- Stage-04 production remediation items carried by PR #13.

### Known limitations at this tag

- CI had never actually executed on GitHub at the time of tagging.
- Frontend had no test runner; `npm test` did not exist.
- Three-role E2E and the paywall journey were not executed.

---

## [0.3.0] — 2026-08-21

Corresponds to the security, privacy and trust hardening stage (Master Prompt
03; `docs/agent-reports/security-hardening-report.md`, decision: CONDITIONAL
PASS). No SemVer tag was created at the time.

### Added

- Audit logging (`audit_logs`, OWASP A09) and GDPR delete-on-request support.
- Security headers on every response including errors: CSP, `X-Frame-Options:
  DENY`, `nosniff`, Referrer-Policy, Permissions-Policy, COOP, CORP.
- Production configuration fail-fast: `Settings.validate_runtime()` rejects a
  default or short `SECRET_KEY`, an empty `REDIS_URL`, and `COOKIE_SECURE=false`.
- Per-IP login rate limiting (5/min) and brute-force lockout (5 failures →
  15 minutes), with constant-work password comparison on a miss.

### Changed

- Cookie-based auth with httpOnly access/refresh cookies and a readable
  `csrf_token` for double-submit CSRF on refresh and logout.
- `python-jose` replaced by `PyJWT` — the former's transitive `ecdsa`
  dependency carried the unfixed PYSEC-2026-1325 advisory (IR-SEC-002).

### Fixed

- **Demo accounts were seeded unconditionally, including under
  `APP_ENV=production`**, where `admin@smartdecor.dev / Admin123!` was a
  working login (B-1 / IR-001). Seeding is now opt-in via
  `SEED_DEMO_ACCOUNTS` and can never run in production.
- The published demo-credentials hint is compiled out of production bundles.
- Logout no longer skipped the server call when no `localStorage` token existed
  — precisely the cookie-auth case, in which the session previously survived
  "Sign out" until the refresh cookie expired.

---

## [0.2.0] — 2026-08-20

The "V2 strict mode" line: phases 0A→5 (research, security, performance, UI
rebuild, dead keys, accessibility), plus the V3 realistic Persian dataset
integration. Historical tags: `v2-phase0-audit-complete`,
`v2-phase2-performance`, `v2-phase3-ui`, `v2-phase4-deadkeys`, `v2-final`,
`v2-datasets-realistic`, `v2-datasets-realistic-merged`.

### Added

- Product feedback API (👍/👎, 3 operations) that re-ranks subsequent
  recommendations (`product_feedback` table).
- Design system V2 and a full UI rebuild: command palette, moodboard editor
  with drag/resize and undo/redo, present mode, floorplan page, shopping list
  with a sticky total, optimistic toasts.
- Route-level code splitting and an initial-JS budget.
- Realistic Persian dataset integration (styles, questionnaire, palettes,
  budget ranges) driving the quiz and taxonomy from data rather than code.
- Static dead-keys audit (`scripts/auditDeadKeys.ts`) — every interactive
  control must do something.

### Changed

- Recommendation scoring consolidated into the weighted model recorded in
  ADR-005 (style/colour/budget/material/pattern).

### Fixed

- Stored seller links are sanitised before rendering into `href` (X-01) — a
  `javascript:` URL would otherwise have executed in the SPA's origin.

---

## [0.1.0] — 2026-08-19

Initial implementation.

### Added

- FastAPI backend with a PostgreSQL + pgvector recommendation engine: hard
  filtering (budget, category, room type), semantic embedding search, and
  weighted scoring.
- Three portals — homeowner (register/login, style quiz, ranked
  recommendations, moodboard, shopping list), designer (project dashboard,
  quiz on behalf of a client, share by link/email), admin (product upload,
  AI feature extraction, human review/approval, user and subscription
  management).
- JWT authentication with refresh tokens; bcrypt password hashing.
- Alembic migrations, seed data, Docker Compose stacks, initial CI and
  documentation.

Historical tag: `v1.1-final-p0p1-fixed` marks the P0/P1 fix loop at the end of
this line (45 tests, Postgres parity run, rate limiting).

---

[Unreleased]: https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform/compare/v0.4.0-rc.1...v0.5.0
[0.4.0-rc.1]: https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform/releases/tag/v0.4.0-rc.1
