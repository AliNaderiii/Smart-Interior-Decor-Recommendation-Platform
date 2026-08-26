# Spec-Delta Audit — client advertisement vs codebase

**Stage:** 1 (T-1.7) · **Date:** 2026-08-26 · **HEAD:** branch `arena/01a03cf5-smart-interior-decor-recommend`

Line-by-line diff of the **client advertisement's functional scope** against
what actually exists in this repository. Every contractual bullet gets exactly
one verdict. Nothing is omitted; where a bullet is only partly delivered, the
**gap** is named and routed either to a minimal fix in this stage or to an
`integration-request.md` entry for a later stage.

**Verdicts**

| Verdict | Meaning |
|---|---|
| `IMPLEMENTED` | Present and exercised by a test or a captured probe. Path given. |
| `PARTIAL` | Exists but does not fully meet the bullet. Gap named + routed. |
| `ABSENT` | Not present. Routed. |
| `CLIENT-DECISION` | Cannot be settled without client input or client-supplied data/credentials. |

**Method.** Each row was checked against source, and — where a runtime claim is
made — against the running application. The protocol harness
(`t-1.4b/03-journey-protocol-harness.mjs`, 45/45 green,
log `t-1.4b/02-journey-protocol-harness.log`) exercised the homeowner, designer
and admin flows end to end against the live API. Backend suite at this HEAD:
**549 passed / 22 skipped**.

---

## Portal 1 — Homeowner

| # | Contractual bullet | Verdict | Evidence / gap |
|---|---|---|---|
| 1.1 | Register / login with JWT + refresh token | **IMPLEMENTED** | `backend/app/api/routes/auth.py` (`/register`, `/login`, `/refresh`, `/logout`, `/me`). Default mode issues httpOnly `access_token` + `refresh_token` cookies plus a readable `csrf_token` for double-submit CSRF. Verified live: `t-1.4/00-protocol-auth.log`, `t-1.4b/02-journey-protocol-harness.log`. |
| 1.2 | Style quiz: style, palette, room dimensions, budget, materials | **IMPLEMENTED** | 5 steps, dataset-driven: `frontend/src/pages/QuizPage.tsx`, `frontend/src/assets/questionnaire.json`; persisted by `POST /quiz` (`backend/app/api/routes/quiz.py`, `models/quiz.py` stores `room_width_cm`/`room_length_cm`). |
| 1.3 | 3–5 ranked products per category | **IMPLEMENTED** | `POST /recommend`. Verified live: 7 categories × **5 items each**, all within 3–5 (`t-1.4b/02-journey-protocol-harness.log`). Asserted per-category in `journey-homeowner.spec.ts`. |
| 1.4 | Editable moodboard | **IMPLEMENTED** | `frontend/src/pages/MoodboardEditorPage.tsx` + `components/BoardGrid.tsx` (drag/resize, undo/redo, autosave, present mode); `backend/app/api/routes/moodboards.py` (POST/GET/PATCH/DELETE). |
| 1.5 | 2D room-plan preview | **IMPLEMENTED** | `frontend/src/pages/FloorplanPage.tsx`. Confirmed it renders **from a moodboard**: it queries `/moodboards`, loads the first board and offers "Add from your moodboard" using real product dimensions (`FloorplanPage.tsx` lines 48–54, 414–416); PNG export included. |
| 1.6 | Shopping list with price + direct seller link | **IMPLEMENTED** | `frontend/src/pages/ShoppingListPage.tsx`: per-line price, quantity stepper, sticky total, per-item seller link. Links are sanitised through `safeUrl()` before reaching `href` (X-01), and a rejected link renders as nothing rather than a dead anchor. |
| 1.7 | Subscription paywall for full access | **PARTIAL** | The **recommendation** paywall is real and server-side: `POST /recommend` marks results beyond the plan's `recommendations_per_category` as `locked` (`routes/quiz.py:118-135`), and the UI renders a soft blur + "Unlock with Pro" (`ProductCard.tsx`). **Gap:** the `homeowner_free` plan also declares `limits.moodboards: 0` and `limits.floorplans: 0`, and **neither is enforced** — `POST /moodboards` has no plan check, so a free user can create unlimited moodboards and floorplans. → **IR-S1-002**. |

## Portal 2 — Designer (B2B2C)

| # | Contractual bullet | Verdict | Evidence / gap |
|---|---|---|---|
| 2.1 | Professional projects dashboard | **IMPLEMENTED** | `frontend/src/pages/designer/DashboardPage.tsx` (status filters, client avatars, quiz counts); `GET /projects`. |
| 2.2 | Multiple project management | **IMPLEMENTED** | `GET/POST/GET{id}/DELETE /projects` (`backend/app/api/routes/projects.py`); dashboard lists and navigates them. Verified live (2 concurrent projects) in the harness. |
| 2.3 | Take the quiz on behalf of a client | **IMPLEMENTED** | `/quiz?project=<id>` shows a "Client name" field for designers (`QuizPage.tsx`); `POST /quiz` accepts `project_id` + `client_name` and links the quiz to the project. |
| 2.4 | Share results with client via link **or email** | **IMPLEMENTED** | `POST /projects/{id}/share` creates a tokenised share link and, when `send_to_email` is supplied, sends it (`app/services/emailer.py`, Resend-ready). **The UI does send it**: `designer/ProjectPage.tsx` has a share-email input and the button reads "Share & email" when an address is present (lines 25–38, 163–177). Public consumption via `GET /share/{token}` → `SharePage.tsx`. *(Note: this closes the supervisor's open question — share-by-email is not backend-only.)* |
| 2.5 | Subscription required to create new projects | **IMPLEMENTED** | Enforced server-side from the versioned plan dataset (T-1.1): `designer_free`=2, `designer_studio`=20, `designer_agency`=unlimited. Race-safe (row lock + atomic conditional insert) and fails **closed** on unknown plan data. `backend/app/services/designer_quota.py`; 12 tests + a Postgres-gated concurrency proof (`t-1.1/01-quota-suite.log`). Live 402 verified: `t-1.4b/01-designer-quota-402-probe.log`. |
| 2.6 | *(derived)* The quota wall must be legible to the designer | **PARTIAL** → **minimally fixed this stage** | The backend's Persian 402 («سهمیهٔ پروژه‌های شما … اشتراک خود را ارتقا دهید») was **discarded** by the dashboard, which always toasted a generic English "Could not create the project." Fixed minimally in `DashboardPage.tsx` (surface `ApiError.message`), pinned by 5 unit tests (4 of which fail against the pre-fix code) and asserted in `journey-designer.spec.ts`. **Remaining gap (deliberately not built — out of scope per the stage brief):** there is no dedicated upgrade/paywall surface for designers — no plan comparison, no CTA to `/upgrade` from the quota error. → **IR-S1-003**. |

## Portal 3 — Admin

| # | Contractual bullet | Verdict | Evidence / gap |
|---|---|---|---|
| 3.1 | Product upload/management with image + base info | **IMPLEMENTED** | `POST /products/upload` (magic-byte sniffed, bounded, re-encoded, generated storage key), plus `POST/PATCH/DELETE /products`; `frontend/src/pages/admin/ProductsPage.tsx` (list, filter, paginate, bulk actions). Verified live (201 + draft created). |
| 3.2 | AI feature extraction (colour, style, material, dimensions) | **IMPLEMENTED** | `ai/` feature extractor behind `AI_PROVIDER`. Live mock run returned `colors`, `style`, `material`, `patterns`, `confidence`, `needs_review` (`t-1.4b/02-journey-protocol-harness.log`). Model output is treated as untrusted input (`_clean_ai_text`). *(Real-provider accuracy is a separate acceptance item — see 5.4.)* |
| 3.3 | Manual review / approval (human-in-the-loop) | **IMPLEMENTED** | Uploads land `is_verified=False` (confirmed live). Reviewer UI: JSON editor with a live diff **against the AI's original extraction**, confidence triage sort, single and bulk `POST /products/{id}/verify`. Verified end-to-end (pending → verified) in the harness and asserted in `journey-admin.spec.ts`. |
| 3.4 | Style-taxonomy management (modern/scandinavian/industrial/…) | **PARTIAL** | **Read-only.** `GET /admin/taxonomy` returns the taxonomy; there is **no** create/update/delete endpoint (`routes/admin.py:122-125`). The taxonomy is a static dataset (`frontend/src/assets/style_taxonomy.json`, backend constants). Admins can *assign* existing styles to a product via the review dialog's taxonomy chips, but cannot **manage** the taxonomy itself — adding a style requires a code/dataset change and a deploy. → **IR-S1-004**. |
| 3.5 | User & subscription management | **PARTIAL** | Users: `GET /admin/users` + `PATCH /admin/users/{id}` (role/status) with a UI — implemented. Subscriptions: `GET /admin/subscriptions` and a UI table are **read-only**; there is no admin endpoint to grant, extend, downgrade or cancel a subscription. → **IR-S1-005**. |

## Recommendation engine

| # | Contractual bullet | Verdict | Evidence / gap |
|---|---|---|---|
| 4.1 | Hard filter (budget, category, room type) | **IMPLEMENTED** | Stage A SQL filter on `room_type` + `category` + budget window + `is_verified` (`services/recommender.py:274-290`), backed by the composite index `ix_products_filter`. |
| 4.2 | Semantic embedding search | **IMPLEMENTED** | Stage B: pgvector cosine (`style_embedding <=> :emb LIMIT 100`) on Postgres, Python cosine fallback on SQLite (`recommender.py:294-340`). `EMBEDDING_BACKEND=clip\|hash`. |
| 4.3 | Weighted scoring — style 30 / colour 30 / budget 20 / material 15 / pattern 10 | **CLIENT-DECISION (C-6)** | The advertised weights **sum to 105 %**. Handled in T-1.2 by two validated profiles: `current` (default, material .15 / pattern .05) and `client-ad` (material **.10** / pattern .10 — the excess absorbed by `material`). A profile that does not sum to 1.0 is refused at boot. Both profiles evaluated over 18/18 scenarios with per-category rank deltas: `docs/reports/weights_profiles.md`. **The client must confirm which signal absorbs the 5 points.** |
| 4.4 | 3–5 ranked output | **IMPLEMENTED** | See 1.3. |
| 4.5 | Room dimensions influence the result | **PARTIAL** | Room dimensions are **collected** (quiz step 3) and **stored** (`quizzes.room_width_cm/room_length_cm`), and products carry `width_cm`/`depth_cm`/`height_cm` — but the recommender **never reads them**: no dimensional filter and no dimensional scoring term (`grep room_width services/recommender.py` → only the docstring). A sofa too large for the room can be ranked #1. The advertisement lists room dimensions as a quiz input rather than an explicit scoring signal, so this is a *reasonable-expectation* gap rather than a literal breach — but it is a real one. → **IR-S1-006**. |
| 4.6 | p95 < 2 s | **IMPLEMENTED (dev evidence)** | `tests/test_recommender.py::test_30_p95_latency_under_2s` — 100 sequential varied requests, cache off. **30/30 recommender tests pass** at this HEAD (spec floor: ≥28/30). Postgres-backed p95 at HEAD is Stage-2 evidence (last measured 1625 ms @ `a847ad5`). |

## Security

| # | Contractual bullet | Verdict | Evidence / gap |
|---|---|---|---|
| 5.1 | TLS 1.3 | **IMPLEMENTED (config); UNVERIFIED at runtime** | `Caddyfile`: `tls internal { protocols tls1.3 tls1.3 }`. Cannot be probed here (no Docker in the sandbox); belongs to deployment verification (Stage 4/5). |
| 5.2 | bcrypt | **IMPLEMENTED** | `passlib` `CryptContext(schemes=["bcrypt"])` (`app/core/security.py:26`). Login also does constant-work dummy hashing on a miss so a wrong email and a wrong password cost the same. |
| 5.3 | Encryption at rest (KMS or equivalent) | **PARTIAL** | Fernet at-rest encryption exists with a documented path to a cloud KMS (`app/core/security.py`), and production boot refuses an unset/invalid `FERNET_KEY` (`config.py:272-286`). **Gap:** the "equivalent" is a single static application key, not a managed KMS with rotation and audit; no key-rotation procedure is implemented. Deployment/Stage 4–5 scope. → **IR-S1-007**. |
| 5.4 | GDPR delete on request | **PARTIAL** | The backend is complete: `DELETE /api/v1/users/me` hard-deletes the user and all owned data (feedback, share links, payments, quizzes, moodboards…) and pseudonymises audit rows; `GET /users/me/export` provides portability. **Gap:** there is **no UI anywhere in the SPA** that calls either endpoint (`grep` over `frontend/src` → 0 hits), so a user cannot in practice exercise the right without contacting support and someone using the API by hand. → **IR-S1-008**. |
| 5.5 | No payment-data storage | **IMPLEMENTED** | No card/PAN/CVV fields exist in any model; `models/subscription.py:31` states the constraint explicitly. Payment goes through a provider abstraction (`PAYMENT_PROVIDER`) that stores only a provider reference and status. |

## Acceptance criteria (Stage 2/5 evidence items)

Per the stage brief these are **blocked-pending**, not failures.

| # | Criterion | Verdict | Status |
|---|---|---|---|
| 6.1 | Lighthouse ≥ 80 | **CLIENT-DECISION / BLOCKED** | No Chrome in this sandbox (BL-6). The CI `lighthouse` job enforces `performance ≥ 80` and fails otherwise. Stage 2. |
| 6.2 | LCP < 3 s | **CLIENT-DECISION / BLOCKED** | Same job asserts `LCP ≤ 3000 ms` and `TTI ≤ 4000 ms`. Stage 2. |
| 6.3 | ≥ 28/30 recommender tests | **MET** | **30/30 pass** at this HEAD (`tests/test_recommender.py`). The only acceptance criterion that can be, and is, satisfied locally. |
| 6.4 | AI extraction ≥ 80 % on 50 images | **CLIENT-DECISION / BLOCKED (B-5)** | MOCK mode benchmarks at 100 %, which proves the harness, not the model. REAL mode needs a provider credential (**C-1**). |
| 6.5 | All seller links valid | **CLIENT-DECISION / BLOCKED (BL-5)** | Sandbox egress is blocked, so a local run reports 0/100 for network reasons, not link quality. Needs egress or the client's real catalogue (**C-5**). |

---

## Summary

| Verdict | Count |
|---|---:|
| IMPLEMENTED | 20 |
| PARTIAL | 8 |
| ABSENT | 0 |
| CLIENT-DECISION / BLOCKED | 5 |
| **Total bullets audited** | **33** |

**No contractual bullet is entirely absent.** Every one of the three portals,
the engine and the security list has a working implementation; the eight
PARTIALs are gaps at the edges of otherwise-delivered features.

### Fixed in this stage (minimal, per PM judgment)

- **2.6** — the designer quota's Persian 402 now reaches the user
  (`DashboardPage.tsx`, one-line change + 5 pinning unit tests). Chosen because
  it is the user-visible half of T-1.1's own deliverable: enforcing a quota the
  user cannot understand is an incomplete feature, not a new one.

### Routed to `integration-request.md` (not built here)

| ID | Gap | Suggested stage |
|---|---|---|
| IR-S1-002 | `homeowner_free` `moodboards: 0` / `floorplans: 0` limits are declared but never enforced | Stage 2 (product) |
| IR-S1-003 | No designer upgrade/paywall surface (explicitly out of scope for Stage 1) | Stage 2 (product) |
| IR-S1-004 | Style taxonomy is read-only — no management CRUD | Stage 2 (product) |
| IR-S1-005 | Subscription administration is read-only — no grant/extend/cancel | Stage 2 (product) |
| IR-S1-006 | Room dimensions are collected and stored but ignored by the recommender | Stage 2 (AI/product) |
| IR-S1-007 | At-rest encryption uses a static Fernet key, not a managed KMS with rotation | Stage 4/5 (deployment) |
| IR-S1-008 | GDPR delete/export have no UI — the right cannot be exercised by a user | Stage 3 (compliance) |

### Open client decisions

- **C-6** — which weight absorbs the advertisement's 5-point excess (currently
  `material`, .15 → .10). Comparison evidence: `docs/reports/weights_profiles.md`.
- **C-1** — AI provider credential, required for the real-mode extraction benchmark.
- **C-5** — the real product catalogue, required for seller-link validation.
