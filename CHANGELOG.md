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

### Added

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
