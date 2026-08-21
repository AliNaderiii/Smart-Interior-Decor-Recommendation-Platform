# Security, Privacy & Trust Hardening — Stage 03 report

**Stage:** Master Prompt 03 — Security, Privacy & Trust Hardening
**Role:** Security & Privacy Hardening Lead (CISO/supervisor, FastAPI security engineer,
frontend AppSec engineer, DevSecOps engineer, GDPR specialist, threat-modelling
analyst, pentest QA)
**Repository:** `AliNaderiii/Smart-Interior-Decor-Recommendation-Platform`
**Base branch:** `v2-strict-mode` · **Branch:** `agent/security-hardening-2026-08-21`
**Branched from:** `2f0338c14718b7a38b167d195e4ec497a94a122b`
**Date:** 2026-08-21

## Decision: **CONDITIONAL PASS**

Every in-scope security objective is implemented, tested and evidenced. The
top-priority requirement — *production must never automatically create
predictable demo users or default admin credentials* — is closed with four
independent locks and reproducible before/after proof, while local development
convenience is preserved unchanged behind an explicit opt-in.

The condition is that **seven findings need owners outside this stage's file
scope** (IR-SEC-001…007), and three of them matter before a real launch: the
security scans and probes are not yet in CI (IR-SEC-006), audit-log retention is
promised to data subjects but not enforced (IR-SEC-007), and one unfixable
dependency advisory remains accepted rather than removed (IR-SEC-002). None is
exploitable as the code stands; all are recorded in `integration-request.md`
with the exact files to change.

---

## 1. Headline result

| Measure | Before | After |
| --- | --- | --- |
| Black-box API probe (37 checks) | **16 secure / 21 INSECURE** | **37 secure / 0 INSECURE** |
| Production seeding probe (3 production cases) | **3/3 created a working `admin@smartdecor.dev / Admin123!`** | **0/3 create any user** |
| Production fail-safe probe (8 checks) | not previously testable | **8 secure / 0 INSECURE** |
| Backend test suite | 97 passed | **376 passed, 8 skipped** (+279 new tests) |
| Login timing oracle | 268.1 ms vs 9.1 ms = **29.3×** | 265.6 ms vs 265.3 ms = **1.0×** |
| Frontend build / lint | — | build clean, **0 errors**, 12 pre-existing warnings |
| Demo credentials in the production bundle | present on the login page | **absent** |

---

## 2. What was done

### 2.1 Recon, before touching anything

1. Read `agent-master-prompts/00-README.md` and `03-security-privacy.md`; confirmed
   the allowed file list and the "integration request, not direct edit" rule.
2. Read `docs/agent-reports/baseline-release-report.md` (CONDITIONAL PASS, 12
   production blockers, B-1 = demo accounts) and all eleven existing integration
   requests.
3. Traced **every** account-creation path in the repository. Exactly two sites
   created users: `backend/scripts/load_realistic_products.py::ensure_default_accounts`
   (~line 107) and an inline block in `backend/scripts/seed_products.py::seed`
   (~line 232). `docker-compose.yml:44-47` runs the first on every backend start.
4. Built a venv, ran the suite to establish the baseline (**97 passed**), and
   captured `00-environment.txt` / `01-git-state.txt`.
5. Stood up **real infrastructure** so the evidence is not fakeredis-shaped:
   Redis 6.2.14 (redislite) on `127.0.0.1:6399` and PostgreSQL 16.2 + pgvector
   0.6.2 (pgserver). No docker or root is available in this sandbox; this was
   the substitute, and it is stated wherever it matters.
6. Wrote two probe harnesses, ran them against the **unmodified** tree, and
   committed the results as evidence *before* writing a single fix
   (commit `d56b6be`).
7. Wrote the STRIDE threat model (11 assets, 10 trust boundaries, threats
   T-01…T-46, two attack trees, a GDPR Art. 30 inventory) and committed it
   (`b08853b`) so the fixes could be reviewed against a stated model.

### 2.2 The top-priority requirement — demo accounts

The credential list now lives in exactly one module,
`backend/app/core/demo_seed.py`, behind a gate with four independent locks:

| Lock | Mechanism | Overridable? |
| --- | --- | --- |
| 1 | `demo_seeding_allowed()` returns `False` under `APP_ENV=production` and logs `CRITICAL` | **No** |
| 2 | `Settings.validate_runtime()` refuses to boot a production process with `SEED_DEMO_ACCOUNTS=true` | **No** |
| 3 | Lifespan guard `assert_no_demo_accounts_in_production()` refuses to serve a production database that already contains demo rows | Only via `REFUSE_DEMO_ACCOUNTS_IN_PRODUCTION=false` |
| 4 | `enable_for_this_process()` (the `--seed-demo-accounts` CLI flag) **raises** under production instead of silently no-op'ing | **No** |

Lock 3 is the one that covers what configuration cannot: a staging dump restored
into production, or a deployment made before this fix.

**Development convenience is preserved exactly.** `SEED_DEMO_ACCOUNTS=true` in a
non-production environment recreates the same three logins, with a `WARNING`
naming them. `docs/security/DEMO_ACCOUNTS.md` documents the switch, the
`DEMO_ACCOUNT_PASSWORD` override, and an incident runbook for finding these
accounts in a production database.

`tests/test_demo_seeding.py` additionally asserts that the passwords appear as
string literals in **no module other than `demo_seed.py`** — a second copy is
how this fix would quietly be undone.

### 2.3 Backend security changes

New modules under `backend/app/core/`:

| Module | Purpose |
| --- | --- |
| `demo_seed.py` | The gate above; the single home of the demo credentials |
| `url_safety.py` | Scheme allowlist, DNS resolution, private/loopback/link-local/reserved rejection — the SSRF and `javascript:` control |
| `uploads.py` | Bounded streaming read, magic-byte sniffing, decompression-bomb limits, re-encode (kills polyglots and EXIF), generated object keys |
| `log_redaction.py` | `setLogRecordFactory` + `RedactingFilter`: JWTs, bearer/basic, `token=`/`key=`/`password=`, cookies, PANs, emails → keyed pseudonym |

Changed modules:

* **`config.py`** — production fail-fast extended to `SEED_DEMO_ACCOUNTS`, a
  non-https `FRONTEND_ORIGIN`, `SameSite=none` without `Secure`, a missing or
  invalid `FERNET_KEY`, `STORAGE_BACKEND=local`, an AI provider without a key,
  and a JWT-algorithm allowlist enforced in *every* environment. All problems
  are reported at once.
* **`rate_limit.py` / `brute_force.py`** — **fail closed** in production
  (`503` + `Retry-After`), documented fail-open in dev/test. Previously a Redis
  outage silently disabled every throttle and lockout: a two-step
  "DoS Redis, then brute-force freely" bypass.
* **`redis_client.py`** — refuses to hand a per-process fakeredis client to a
  production process.
* **`security_headers.py`** — headers applied inside the middleware's own
  exception path (a `500` previously bypassed the middleware entirely and came
  back bare), `script-src 'self'` with no `unsafe-inline`, `img-src` derived
  from the configured CDN (closes IR-005), `upgrade-insecure-requests` in
  production, `Cache-Control: no-store` + `Vary: Cookie, Authorization, Origin`.
* **`storage.py`** — extension allowlist (`.bin` for anything unknown) and a
  storage-root containment assertion.
* **`auth.py`** — constant-work bcrypt on the unknown-user path (closes the 29×
  timing oracle); CSRF enforced on `/refresh` and `/logout` **when and only
  when** the credential arrives in a cookie.
* **`users.py`** — GDPR export (Art. 15/20) and an erasure that pseudonymises
  the audit trail instead of orphaning or destroying it.
* **`admin.py`** — `extra="forbid"`, role pattern, no self-demotion or
  self-deactivation, refusal to remove the last active admin, audited role
  changes with old → new.
* **`products.py`** — validated uploads, per-admin upload throttle, AI output
  HTML-stripped before persistence (prompt injection is a stored-XSS channel),
  audit rows for upload / rejection / verify.
* **`projects.py` / `moodboards.py` / `subscriptions.py`** — share-view rate
  limit, HTML-escaped email body, `extra="forbid"`, delete/share audit rows.
* **`link_checker.py`** — validates up front with `resolve=True`, then follows
  redirects **manually**, re-validating every hop.
* **`schemas/auth.py`** — 12–72 byte passwords (bcrypt truncates past 72 bytes,
  so the old 128-char bound silently made two different passwords equivalent),
  a banned list, and rejection of repetitive/sequential strings per NIST
  SP 800-63B §5.1.1.2.

### 2.4 Frontend security changes

* **`src/lib/safeUrl.ts`** (new) — the last-line guard for anything reaching an
  `href`. Strips control characters before inspecting the scheme (`java\tscript:`
  is parsed as `javascript:` by browsers), allowlists `http`/`https`/`mailto`/`tel`,
  resolves protocol-relative URLs. Applied at all three `seller_link` render
  sites, including the **unauthenticated** share page.
* **`src/pages/LoginPage.tsx`** — the demo-credential block is wrapped in
  `import.meta.env.DEV`, so Vite removes it from production bundles entirely.
  Verified by grepping `dist/`.
* **`src/stores/authStore.ts`** — tokens are no longer duplicated into
  `localStorage` when the backend has issued httpOnly cookies, and only the
  profile is persisted. Keeping a readable copy of a token that was
  deliberately made unreadable defeats the cookie migration.
* **`src/components/Layout.tsx`** — "Sign out" now **always** calls
  `POST /auth/logout`. It previously skipped the call whenever `localStorage`
  was empty — i.e. exactly the cookie-auth case — so the session survived logout
  until the refresh cookie expired.
* **`src/lib/api.ts`** — exports `usingCookieAuth()`, the signal the store uses.

### 2.5 Tests

279 new tests across nine modules, all negative/adversarial in character:

| Module | Tests | Covers |
| --- | --- | --- |
| `test_demo_seeding.py` | 17 | The gate, the boot guard, both real seed entrypoints as subprocesses, credential-duplication scan |
| `test_auth_hardening.py` | 32 | Lockout, throttles + `Retry-After`, password policy, timing, cookie flags, CSRF, rotation/revocation, `alg:none`, tampered signatures |
| `test_idor_rbac.py` | 48 | Cross-tenant read/write on every resource, hostile identifiers, the full role matrix, admin self-lockout, audited role changes |
| `test_input_validation.py` | 45 | 10 XSS payloads at rest, AI prompt injection, oversized/typed/nested input → 422 not 500, mass assignment, SQL injection |
| `test_upload_security.py` | 28 | HTML/SVG/PE/polyglot rejection, traversal, bombs, EXIF GPS stripping, per-admin throttle, storage containment |
| `test_url_safety.py` | 34 | 9 dangerous schemes, 12 SSRF targets, DNS rebinding, per-hop redirect revalidation |
| `test_gdpr.py` | 29 | Erasure completeness, audit pseudonymisation, export contents/scope/throttle, log redaction |
| `test_security_headers.py` | 20 | Headers on 200/401/403/404/405/422/429/**500**, caching, CORS, CSP, production surface |
| `test_config_fail_safe.py` | 26 | Boot fail-fast per setting, fakeredis refusal, fail-closed 503 vs fail-open dev |
| `test_redis_real.py` | 8 | Real shared Redis: cross-client counters, TTLs, lockout, blacklist (skips without `TEST_REDIS_URL`) |
| `frontend/tests/unit/safeUrl.test.ts` | 9 | `javascript:` in seven disguises, other schemes, relative URLs, malformed input |

---

## 3. Files changed

**59 files, +6355 / −228.**

<details>
<summary>Backend — new (6)</summary>

```
backend/app/core/demo_seed.py
backend/app/core/log_redaction.py
backend/app/core/uploads.py
backend/app/core/url_safety.py
backend/tests/test_auth_hardening.py
backend/tests/test_config_fail_safe.py
backend/tests/test_demo_seeding.py
backend/tests/test_gdpr.py
backend/tests/test_idor_rbac.py
backend/tests/test_input_validation.py
backend/tests/test_redis_real.py
backend/tests/test_security_headers.py
backend/tests/test_upload_security.py
backend/tests/test_url_safety.py
```
</details>

<details>
<summary>Backend — modified (22)</summary>

```
backend/app/api/routes/admin.py          backend/app/core/redis_client.py
backend/app/api/routes/auth.py           backend/app/core/security_headers.py
backend/app/api/routes/moodboards.py     backend/app/core/storage.py
backend/app/api/routes/products.py       backend/app/main.py
backend/app/api/routes/projects.py       backend/app/models/audit_log.py
backend/app/api/routes/subscriptions.py  backend/app/schemas/auth.py
backend/app/api/routes/users.py          backend/app/schemas/product.py
backend/app/core/brute_force.py          backend/app/services/link_checker.py
backend/app/core/config.py               backend/scripts/load_realistic_products.py
backend/app/core/cookies.py              backend/scripts/seed_products.py
backend/app/core/rate_limit.py           backend/tests/conftest.py
```
</details>

<details>
<summary>Frontend (8)</summary>

```
frontend/src/lib/safeUrl.ts              (new)
frontend/tests/unit/safeUrl.test.ts      (new)
frontend/src/lib/api.ts
frontend/src/stores/authStore.ts
frontend/src/components/Layout.tsx
frontend/src/components/ProductCard.tsx
frontend/src/pages/LoginPage.tsx
frontend/src/pages/SharePage.tsx
frontend/src/pages/ShoppingListPage.tsx
```
</details>

<details>
<summary>Documentation and evidence (17)</summary>

```
docs/agent-reports/security-hardening-report.md              (this file)
docs/security/THREAT_MODEL.md
docs/security/RISK_REGISTER.md
docs/security/DEMO_ACCOUNTS.md
docs/security/PRODUCTION_SECURITY_CHECKLIST.md
docs/security/probes/probe_demo_seeding.py
docs/security/probes/probe_api_security.py
docs/security/probes/probe_production_failsafe.py
docs/agent-reports/security-hardening-evidence/00-environment.txt
docs/agent-reports/security-hardening-evidence/01-git-state.txt
docs/agent-reports/security-hardening-evidence/03-BEFORE-demo-seeding-probe.txt
docs/agent-reports/security-hardening-evidence/04-BEFORE-api-security-probe.txt
docs/agent-reports/security-hardening-evidence/05-AFTER-demo-seeding-probe.txt
docs/agent-reports/security-hardening-evidence/06-AFTER-api-security-probe.txt
docs/agent-reports/security-hardening-evidence/07-AFTER-production-failsafe-probe.txt
docs/agent-reports/security-hardening-evidence/08-AFTER-pytest-full-suite.txt
docs/agent-reports/security-hardening-evidence/09-AFTER-pytest-real-redis.txt
docs/agent-reports/security-hardening-evidence/10-pip-audit.log
docs/agent-reports/security-hardening-evidence/11-AFTER-frontend-verification.txt
integration-request.md
```
</details>

**Not touched, deliberately:** `docker-compose.yml`, `backend/requirements.txt`,
`backend/ai/**`, `frontend/package.json`, `.github/workflows/**` — all out of
scope, all raised as integration requests instead.

---

## 4. Security findings — before and after

### 4.1 The 21 insecure probe checks at baseline, and their disposition

| Check | Baseline finding | Fix | Now |
| --- | --- | --- | --- |
| `H-01` | An unhandled `500` carried **no** security headers — the middleware was bypassed | Headers applied in the middleware's own exception path | SECURE |
| `H-03` | The `422` envelope reflected the submitted value (self-XSS, password disclosure) | Field name + type only, never the input | SECURE |
| `C-02` | Production CORS allowed `http://localhost:5173/4173` with credentials | Origins built per environment; production = one https origin | SECURE |
| `X-01` | `javascript:` accepted in `seller_link`, rendered into `<a href>` on the public share page | Server-side scheme allowlist + `safeUrl()` at render | SECURE |
| `X-02` | Admin-supplied product text stored as raw markup | `SafeText` HTML-stripping | SECURE |
| `X-03` | AI-generated copy stored verbatim — prompt injection → stored XSS | `_clean_ai_text()` strips and bounds model output | SECURE |
| `V-01` | `ProductIn` accepted `id` and `is_verified` (mass assignment) | `extra="forbid"` | SECURE |
| `V-03` | `category` was a free string | Taxonomy validation | SECURE |
| `V-04` | `UserPatch` accepted unknown fields | `extra="forbid"` + role pattern | SECURE |
| `U-01` | `evil.html` with `<script>` accepted and served same-origin as `text/html` | Magic-byte sniffing, four-format allowlist, generated key | SECURE |
| `U-02` | SVG accepted (a scriptable document format) | Rejected | SECURE |
| `U-03` | PE binary declared `image/jpeg` accepted | Sniffing beats the declared type | SECURE |
| `U-04` | Traversal filename reached the storage layer | UUID key + containment assertion | SECURE |
| `U-05` | 12 consecutive uploads, each costing an AI inference, all `201` | Per-admin rate limit + `Retry-After` | SECURE |
| `R-01` | Unauthenticated `GET /share/{token}` unthrottled | Per-IP limit + token length guard | SECURE |
| `A-06` | An admin could demote itself → permanent platform lockout | `409` on self role-change/deactivation; last-admin refusal | SECURE |
| `L-01` | Role changes left no audit trail | `role_change` row with actor and old → new | SECURE |
| `G-02` | Erasure left `audit_logs` (IP + UA) bound to the deleted user id | Pseudonymised: keyed HMAC id, IP → /24 or /48, UA dropped | SECURE |
| `G-03` | The erasure itself was not audited | One `user_delete` row, written already carrying the pseudonym | SECURE |
| `P-01` | Raw email addresses in log streams | Redacting log factory + filter | SECURE |
| `T-01` | Login timing 268.1 ms vs 9.1 ms = **29.3×** user-enumeration oracle | Constant-work dummy bcrypt on the miss path | SECURE (1.0×) |

### 4.2 One subtlety worth recording

`G-02` initially still failed after the fix. `SessionLocal` is configured with
`autoflush=False` (`app/db/session.py:41`), so the `user_delete` row added
before the bulk `UPDATE audit_logs` was not yet in the database when that
statement ran — it flushed afterwards, carrying the real user id. The erasure
now pseudonymises first, flushes explicitly, and then inserts a row that already
contains the pseudonym. This is the kind of defect that only a test against a
real database finds.

---

## 5. Exact commands and results

All commands run from the repository root unless stated.

```bash
# Backend suite (baseline was 97 passed)
cd backend && .venv/bin/python -m pytest -p no:warnings
→ 376 passed, 8 skipped in 71.60s
   (the 8 skips are tests/test_redis_real.py, which needs TEST_REDIS_URL)

# The same tests against a real, shared Redis
TEST_REDIS_URL=redis://127.0.0.1:6399/9 .venv/bin/python -m pytest tests/test_redis_real.py -v
→ 8 passed in 4.16s   (redis_version: 6.2.14, ping: True)

# Black-box API probe, against real PostgreSQL 16.2 + real Redis 6.2.14
PROBE_REDIS_URL=redis://127.0.0.1:6399/5 \
PROBE_DB_URL="postgresql+psycopg://postgres@/postgres?host=/tmp/pgdata-evidence" \
  .venv/bin/python ../docs/security/probes/probe_api_security.py --label AFTER
→ SUMMARY AFTER: 37 checks, 37 secure, 0 INSECURE
   (baseline on the same harness: 37 checks, 16 secure, 21 INSECURE)

# Demo-account seeding probe (6 cases, subprocesses, throwaway databases)
.venv/bin/python ../docs/security/probes/probe_demo_seeding.py
→ VERDICT: production runs that created demo accounts = 0  (requirement: 0)
   development + SEED_DEMO_ACCOUNTS=true → 3 accounts, as documented

# Production fail-safe probe (8 checks, production-shaped child processes)
.venv/bin/python ../docs/security/probes/probe_production_failsafe.py
→ SUMMARY: 8 checks, 8 secure, 0 INSECURE

# Lint
.venv/bin/ruff check app tests
→ 1 error: I001 in tests/test_perf_v2.py  (PRE-EXISTING, owned by Stage 04 — IR-002)
.venv/bin/ruff check app
→ All checks passed!

# Dependency advisories
.venv/bin/pip-audit -r requirements.txt
→ Found 1 known vulnerability in 1 package
   ecdsa 0.19.2  PYSEC-2026-1325  (no fix available — accepted, IR-SEC-002)

# Frontend
cd frontend && npm ci && npm run build
→ ✓ built in 701ms   (tsc -b clean)
npm run lint
→ Found 12 warnings and 0 errors   (all 12 pre-existing)
node --experimental-strip-types --test tests/unit/safeUrl.test.ts
→ # pass 9  # fail 0
grep -rl 'Admin123|Demo1234|Design123' dist/
→ (no matches — the demo hint is compiled out of production builds)
```

### Infrastructure notes (stated honestly)

* No docker and no root in this sandbox. `apt-get install redis-server` is not
  available. Real Redis 6.2.14 was obtained via **redislite** and real
  PostgreSQL 16.2 + pgvector 0.6.2 via **pgserver**, both bound to localhost.
  Every "real Redis" and "real PostgreSQL" claim above refers to those servers.
* Still genuinely blocked, unchanged from the baseline stage and **not**
  simulated: real-model AI calls, real CLIP embeddings, live seller-link checks,
  Lighthouse, Playwright E2E, Docker image builds, CI activation.

---

## 6. Evidence paths

All under `docs/agent-reports/security-hardening-evidence/`:

| File | Contents |
| --- | --- |
| `00-environment.txt` | Toolchain and interpreter versions |
| `01-git-state.txt` | Branch point and clean-tree proof |
| `03-BEFORE-demo-seeding-probe.txt` | **Baseline: 3/3 production runs create `admin@smartdecor.dev / Admin123!`** |
| `04-BEFORE-api-security-probe.txt` | **Baseline: 37 checks, 16 secure, 21 INSECURE** |
| `05-AFTER-demo-seeding-probe.txt` | **0 production runs create any user; development opt-in still works** |
| `06-AFTER-api-security-probe.txt` | **37 checks, 37 secure, 0 INSECURE** (real PostgreSQL + real Redis) |
| `07-AFTER-production-failsafe-probe.txt` | **8 checks, 8 secure, 0 INSECURE** — boot refusal, DB guard, fail-closed 503, attack surface |
| `08-AFTER-pytest-full-suite.txt` | Full suite: 376 passed, 8 skipped |
| `09-AFTER-pytest-real-redis.txt` | 8 passed against Redis 6.2.14 |
| `10-pip-audit.log` | `ecdsa 0.19.2 / PYSEC-2026-1325`, no fix available |
| `11-AFTER-frontend-verification.txt` | Build, lint, `safeUrl` tests, and the credential grep over `dist/` |

Supporting documents: `docs/security/THREAT_MODEL.md`,
`docs/security/RISK_REGISTER.md`, `docs/security/DEMO_ACCOUNTS.md`,
`docs/security/PRODUCTION_SECURITY_CHECKLIST.md`, and the three re-runnable
probes in `docs/security/probes/`.

---

## 7. Mandatory verification list

| # | Requirement | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Production does not seed demo/admin credentials | **PASS** — 0/3, including with `SEED_DEMO_ACCOUNTS=true` explicitly set | `05-…`, probe F-01/F-03/F-04 |
| 2 | Dev/demo mode documented and safe | **PASS** — explicit opt-in, `WARNING` on creation, `DEMO_ACCOUNTS.md` | `05-…`, `DEMO_ACCOUNTS.md` |
| 3 | Wrong-password lockout works | **PASS** — 5 failures → `429`, and the correct password does not bypass it | `test_auth_hardening.py`, probe `R-04` |
| 4 | Rate limits return `Retry-After` | **PASS** — login, registration, upload, share, export, and the fail-closed `503` | `test_auth_hardening.py`, probe `R-03`/`R-04`, F-06 |
| 5 | Cookies and CSRF work | **PASS** — `HttpOnly`/`Secure`/`SameSite`, double-submit incl. `/refresh` and `/logout` | probe `K-01`…`K-03`, `test_auth_hardening.py` |
| 6 | IDOR/RBAC tests pass | **PASS** — cross-tenant returns `404`, full role matrix enforced | `test_idor_rbac.py` (48) |
| 7 | Oversized inputs return `422`, not `500` | **PASS** | `test_input_validation.py`, probe `V-02` |
| 8 | Unknown fields rejected | **PASS** — every write model | probe `V-01`/`V-04` |
| 9 | XSS payloads sanitized | **PASS** — 10 payloads at rest, plus AI prompt injection | probe `X-01`…`X-03` |
| 10 | Upload abuse tests pass | **PASS** — HTML/SVG/PE/polyglot/traversal/bomb/throttle | probe `U-01`…`U-05` |
| 11 | Security headers on success **and** error responses | **PASS** — 200/401/403/404/405/422/429/500 | `test_security_headers.py` |
| 12 | Logs do not expose tokens or PII | **PASS** | probe `P-01`, `test_gdpr.py` |
| 13 | No functional regression | **PASS** — the original 97 tests still pass inside the 376 | `08-…` |

---

## 8. Remaining risks

Full detail in `docs/security/RISK_REGISTER.md`. The ones a reviewer should
weigh before merging:

1. **Security CI does not exist** (IR-SEC-006). Everything above was verified by
   hand. Without CI, the next change can silently undo it — which is precisely
   the failure mode that produced this stage's top finding.
2. **Audit-log retention is promised but not enforced** (IR-SEC-007). The export
   tells data subjects security events are kept 180 days; nothing deletes them.
   That is a data-minimisation gap under GDPR Art. 5(1)(e), not just storage.
3. **`ecdsa` advisory accepted, not removed** (IR-SEC-002). Unreachable in
   practice — HS256 only, with a boot-time algorithm allowlist — but it will
   keep showing up in every scan until `python-jose` is replaced.
4. **`style-src 'unsafe-inline'` remains** (accepted risk A-02). Tailwind v4 and
   framer-motion require it; `script-src` is clean.
5. **The banned-password list has 15 entries** (A-06). Length, byte bounds and
   repetition/sequence checks carry most of the weight; a real breach-corpus
   check needs a product decision (IR-SEC-005).
6. **`X-Forwarded-For` trust** (A-03). Correct behind the intended Caddy
   deployment; any topology where the proxy forwards a client-supplied header
   makes every per-IP control bypassable. Recorded in the checklist as a hard
   requirement.
7. **`ai/feature_extractor.py` lacks the SSRF validator** (IR-SEC-003).
   Defence-in-depth only: every URL reaching it has already been validated
   twice.
8. **Operational gaps outside any stage's code**: no WAF, secrets in `.env`
   rather than a manager, no alerting on the audit log, unrehearsed restores.

---

## 9. Integration requests raised

| ID | Severity | Owner | Title |
| --- | --- | --- | --- |
| IR-SEC-001 | Medium | 07 | `docker-compose.yml` seeding command and dev-shaped env values |
| IR-SEC-002 | Medium | 07 | Swap `python-jose` → `pyjwt` to drop the unfixable `ecdsa` advisory |
| IR-SEC-003 | Low | 05 | SSRF validator missing in `ai/feature_extractor.py` |
| IR-SEC-004 | Medium | 08 | No frontend unit-test runner for the `safeUrl` security tests |
| IR-SEC-005 | Low | 03 / product | No breached-password check at registration |
| IR-SEC-006 | High | 07 | Security scans and probes are not in CI |
| IR-SEC-007 | Medium | 07 / 03 | Audit-log retention promised to users but not enforced |

Written in full to `integration-request.md`, each with evidence, the exact files
to change, and why this stage could not make the change itself.

---

## 10. Commits

Atomic, one logical subject each:

| Commit | Subject |
| --- | --- |
| `d56b6be` | `security(evidence): capture Stage 03 baseline — environment, git state and reproducible pre-hardening probes` |
| `b08853b` | `security(docs): add STRIDE threat model for the platform` |
| *(see the PR)* | The implementation commits listed in the pull request description |

The pull request targets **`v2-strict-mode`** and has **not** been merged, as
required.
