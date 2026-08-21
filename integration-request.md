# Integration Requests — from Stage 01 (Baseline, Release Governance & Repository Hygiene)

**Raised by:** Master Prompt 01 agent squad
**Baseline commit:** `f97bfad371c7a33cb4fe9f52b7c51520a363fb43`
**Branch:** `arena/01a0247e-smart-interior-decor-recommend` (equivalent to `agent/baseline-release-2026-08-21` — see `docs/RELEASE_BASELINE.md` §1.1)
**Date:** 2026-08-21

Every item below is a defect this stage **found and verified with evidence** but
is **forbidden from fixing** by the `Allowed scope` clause of
`agent-master-prompts/01-baseline-release-governance.md` ("You may modify only
root documentation/configuration and release metadata … Do not modify application
source, migrations, package manifests, Docker runtime files, or CI workflow
implementation").

No file listed under "Files to change" was touched by this stage. Verify with
`git diff --stat` on this branch.

---

## IR-001 · CRITICAL · Demo accounts are seeded in production

**Owner:** Master Prompt 03 — Security & Privacy
**Severity:** Critical — remote admin takeover with publicly documented credentials
**Blocker ID:** B-1

### Evidence

`backend/scripts/load_realistic_products.py:107-118`

```python
def ensure_default_accounts(db) -> None:
    defaults = [
        ("admin@smartdecor.dev", "Admin123!", "admin", "Platform Admin"),
        ("designer@smartdecor.dev", "Design123!", "designer", "Sara Designer"),
        ("demo@smartdecor.dev", "Demo1234!", "homeowner", "Demo Homeowner"),
    ]
    for email, password, role, name in defaults:
        if not db.scalar(select(User).where(User.email == email)):
            user = User(email=email, hashed_password=hash_password(password), role=role, full_name=name)
```

The same block exists at `backend/scripts/seed_products.py:229-238`.

`docker-compose.yml:44-47` executes the loader on **every** backend container start:

```yaml
command: >
  sh -c "alembic upgrade head &&
         python scripts/load_realistic_products.py --realistic --expand-to 150 --if-empty --from-json &&
         uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --no-server-header --proxy-headers"
```

`--if-empty` only skips the *product* seed; `ensure_default_accounts(db)` is called
on **both** branches of the `if if_empty and count:` check
(`load_realistic_products.py:129` and `:137`), so the accounts are created regardless.

`backend/app/core/config.py:105-126` (`Settings.validate_runtime`) already fails
fast in production on a default `SECRET_KEY`, an empty `REDIS_URL` and
`COOKIE_SECURE=false` — it has **no** guard for this. Verified by reading the
function; there is no reference to seeding.

The credentials are published in `README.md`, `PHASE0_AUDIT_GUIDE.md`,
`CONTINUATION_PROMPT_V2.md` and `docs/SECURITY_AUDIT_V2.md`.

### Requested change

1. Gate `ensure_default_accounts()` on `settings.APP_ENV != "production"`, or behind an explicit `SEED_DEMO_ACCOUNTS=true` opt-in that defaults to false.
2. Add `Settings.validate_runtime()` refusal if demo seeding is requested while `APP_ENV=production`.
3. Add a regression test asserting no demo user is created with `APP_ENV=production`.

### Files to change (NOT touched by this stage)

- `backend/scripts/load_realistic_products.py`
- `backend/scripts/seed_products.py`
- `backend/app/core/config.py`
- `backend/tests/test_security_v2.py` (new test)

### Done when

`APP_ENV=production python scripts/load_realistic_products.py …` creates zero
users, and a test proves it.

---

## IR-002 · HIGH · CI backend job fails on lint; migration `0003` is SQLite-hostile

**Owner:** Master Prompt 04 (recommender/scripts) with Master Prompt 07 (CI)
**Blocker IDs:** B-3, B-7

### Evidence A — ruff (CI-breaking)

```
$ cd backend && .venv/bin/ruff check app ai scripts
I001 Import block is un-sorted or un-formatted   --> app/api/routes/projects.py:2:1
E401 Multiple imports on one line                --> scripts/seed_perf_products.py:16:1
I001 Import block is un-sorted or un-formatted   --> scripts/seed_perf_products.py:16:1
Found 3 errors.
[*] 3 fixable with the `--fix` option.
```

Full output: `docs/agent-reports/baseline-release-evidence/07-backend-ruff.log`.
`ci/github-ci.yml` runs `ruff check app ai scripts` as a required backend step, so
the workflow is **red on its first execution**.

Root cause in `app/api/routes/projects.py`: `from app.schemas.sanitize import SafeText`
sits at line 10, between the third-party `pydantic` and `sqlalchemy` imports,
instead of in the first-party block.

### Evidence B — alembic on SQLite

```
$ cd backend && DATABASE_URL=sqlite:///./x.sqlite3 .venv/bin/alembic upgrade head
  File ".../alembic/versions/0003_product_feedback.py", line 46, in upgrade
    op.create_unique_constraint(
NotImplementedError: No support for ALTER of constraints in SQLite dialect.
Please refer to the batch mode feature which allows for SQLite migrations
using a copy-and-move strategy.
```

Full traceback: `…/14-alembic-upgrade-sqlite.log`.

Impact: the SQLite dev/CI path is provisioned by `Base.metadata.create_all()` in the
seed scripts, so **the migration chain is never exercised outside Postgres** and
migration/model drift cannot be detected. `docs/REPRODUCIBILITY.md` §6.

### Requested change

1. `ruff check --fix app ai scripts` (3 mechanical import fixes; no behaviour change).
2. Rewrite the constraint in `0003_product_feedback.py` using
   `with op.batch_alter_table("product_feedback") as batch_op: batch_op.create_unique_constraint(...)`
   — and the same for `downgrade()`'s `op.drop_constraint`.
3. Add a CI job step: `alembic upgrade head && alembic downgrade base && alembic upgrade head`.

### Files to change (NOT touched by this stage)

- `backend/app/api/routes/projects.py`
- `backend/scripts/seed_perf_products.py`
- `backend/alembic/versions/0003_product_feedback.py`
- `ci/github-ci.yml`

---

## IR-003 · HIGH · Stale and contradictory documentation in other agents' files

**Owner:** Master Prompt 07 (deployment/CI docs), 04 (AI/data docs), 08 (QA reports), 02 (research)
**Blocker ID:** D-5 … D-9 in `docs/RELEASE_BASELINE.md` §6

This stage corrected `README.md` and `.env.example` (its own scope). The following
files are owned by other agents and were deliberately left untouched.

### Evidence

Measured at `f97bfad`: **97 tests** (`…/03-backend-pytest.log`), per-file breakdown
in `…/22-doc-claim-verification.txt`.

| File:line | Says | Truth at `f97bfad` |
|---|---|---|
| `ci/README.md:13` | "backend pytest (43 tests)" | 97 |
| `docs/reports/ACCEPTANCE_REPORT.md:9,11,29,54` | "45/45 total" | 97 |
| `docs/reports/postgres_parity.md:52,55` | "45 passed" | 97 (and the Postgres run is from `a847ad5`, 2026-08-19) |
| `docs/RESEARCH_V2.md:5` | "45/45 tests green" | 97 |
| `docs/WALKTHROUGH.md:67` | "43 automated tests green" | 97 |
| `docs/DESIGN_SYSTEM.md:22`, `docs/ARCHITECTURE.md:188` | "45" | 97 |
| `docs/ARCHITECTURE.md:64`, `docs/DEPLOYMENT.md:28`, `docs/reports/ACCEPTANCE_REPORT.md:13` | "the committed `backend/seed_data/embeddings_real.json`" | **file does not exist** (`git ls-files` → no match) |
| `docs/DEPLOYMENT.md:114`, `docs/DATASETS_AUDIT.md:49` | references `.env.example.v2` | **file does not exist**; only `.env.example` |
| `docs/AUDIT_V2.md:12-30` | "21 files, 55 interactive elements, 2 PARTIAL" | re-run at HEAD: **31 files, 92 elements, 0 DEAD, 0 PARTIAL** (`…/15-deadkeys-audit.log`) |
| `docs/API.md` | endpoint reference | omits `GET/POST/DELETE /api/v1/feedback` and `GET /api/v1/health`; live surface = 29 paths / 39 operations (`…/19-api-endpoint-inventory.log`) |

### Requested change

1. Update every count to the measured value **and stamp it**: `97 tests — measured at f97bfad, 2026-08-21, SQLite+fakeredis+mock AI`.
2. Either commit `backend/seed_data/embeddings_real.json` or reword all four references to "generate on a networked machine; not committed".
3. Delete or create `.env.example.v2`; today it is a dangling reference.
4. Re-stamp `docs/AUDIT_V2.md` with the HEAD re-run (the result improved — do not silently drop the old numbers, date them).
5. Add `/feedback` and `/health` to `docs/API.md`.
6. Adopt the convention: **every metric in this repository carries the commit and the evidence class (MOCK / LOCAL / STAGING / PRODUCTION) it was measured under.**

### Enforcement available now

`python scripts/audit_docs_links.py` (added by this stage) fails on dangling file
references and is CI-ready.

---

## IR-004 · MEDIUM · Eight environment variables are declared but read by nothing

**Owner:** Master Prompt 06 (payments/storage/email) and 07 (config topology)
**Blocker ID:** D-11

### Evidence

`grep` across `backend/app`, `backend/ai`, `backend/scripts`, `frontend/src`,
`frontend/vite.config.ts`, `frontend/Dockerfile` — **0 references each**
(`…/22-doc-claim-verification.txt` §6):

| Variable | Superseded by |
|---|---|
| `STORAGE_PROVIDER` | `STORAGE_BACKEND` |
| `CDN_URL` | `S3_PUBLIC_BASE_URL` |
| `CORS_ORIGINS` | `FRONTEND_ORIGIN` (single origin only — `app/main.py:49`) |
| `VITE_API_URL` | nothing — `frontend/src/lib/api.ts:22` hardcodes `const BASE_URL = "/api/v1"` |
| `ZARINPAL_SANDBOX` | `PAYMENT_PROVIDER=zarinpal_sandbox` |
| `ZARINPAL_CALLBACK_URL` | `PAYMENT_CALLBACK_URL` |
| `RESEND_FROM_EMAIL` | `EMAIL_FROM` |
| `RESEND_FROM_NAME` | no sender-name support in `app/services/emailer.py` |

An operator who sets `CORS_ORIGINS` for a multi-origin production deployment will
silently get CORS failures — the value is discarded.

This stage **documented** them in `.env.example` as `[UNUSED@f97bfad]` (in scope);
wiring or removing them is not.

### Requested change

Either implement `CORS_ORIGINS` (multi-origin) and `VITE_API_URL` (build-time base
URL), or remove all eight from `.env.example` and `datasets/service_keys_template.env`.
A half-declared variable is worse than an absent one.

### Files to change (NOT touched by this stage)

- `backend/app/core/config.py`, `backend/app/main.py`
- `frontend/src/lib/api.ts`
- `datasets/service_keys_template.env`

---

## IR-005 · MEDIUM · CSP `img-src` host does not match the documented S3 endpoint

**Owner:** Master Prompt 07 — Infrastructure
**Blocker ID:** B-11 / D-10

### Evidence

`Caddyfile:20` — `img-src ... https://*.s3.ir-thr1.arvanstorage.ir`
`backend/app/core/security_headers.py:30` — the identical `img-src ... https://*.s3.ir-thr1.arvanstorage.ir`
`.env.example` — `S3_ENDPOINT=https://s3.ir-thr-at1.arvanstorage.ir`
`docs/DEPLOYMENT.md:62` — `S3_ENDPOINT=https://s3.ir-thr-at1.arvanstorage.ir`

`ir-thr1` ≠ `ir-thr-at1`. The wildcard `*.s3.ir-thr1.…` also would not match a
bucket served as `<bucket>.s3.ir-thr-at1.arvanstorage.ir`. Result: **every
production product image is CSP-blocked** while looking correct in local
development (which uses `STORAGE_BACKEND=local`).

The same CSP is mirrored by `SecurityHeadersMiddleware` — confirmed in
`…/18-api-smoke.log`, where the FastAPI 404 response carries the identical
`content-security-policy` header — so fixing only the Caddyfile is insufficient.

### Requested change

Align both CSP copies with the real endpoint, or make the allowed image origin
configurable from `S3_PUBLIC_BASE_URL` / `CDN_URL`.

### Files to change (NOT touched by this stage)

- `Caddyfile`
- `backend/app/core/security_headers.py:30`

---

## IR-006 · HIGH · CI has never run

**Owner:** Master Prompt 07 — Infrastructure / CI/CD
**Blocker ID:** B-2

### Evidence

- No `.github/` directory exists in the tree.
- The canonical workflow is `ci/github-ci.yml`; `ci/README.md` and `scripts/enable_ci.sh` document the manual activation.
- Cause on record: the agent GitHub App token is rejected when pushing workflow files (`refusing to allow a GitHub App … without 'workflows' permission`).
- This stage did **not** attempt it: activating CI is Prompt 07's scope and requires a permission this session does not hold.

Consequence: the 97-test suite, the ruff gate, the extraction benchmark and the
Lighthouse budget are all advisory. No status check gates any merge, so the
Postgres/pgvector path (BL-1) and Lighthouse (BL-6) have no environment in which
they can be produced at all (`docs/REPRODUCIBILITY.md` §7).

### Requested change

1. Grant the App the `workflows` permission, or have a human run `./scripts/enable_ci.sh` from a PAT-authenticated clone (client decision C-8).
2. **Fix IR-002 first**, otherwise the first run is immediately red.
3. Configure branch protection on `v2-strict-mode` and `main` requiring the `backend`, `frontend` and `lighthouse` checks.

---

## IR-007 · HIGH · No executable frontend test path

**Owner:** Master Prompt 08 — QA & Acceptance Testing
**Blocker ID:** B-4

### Evidence

`frontend/package.json` scripts: `dev`, `build`, `lint`, `preview` — **no `test`**.
`frontend/tests/e2e/deadKeys.spec.ts` (9.2 KB) exists with `@playwright/test` and
`playwright.config.ts`, but no documented or CI command ever invokes it.
`jsdom` and `@types/jsdom` are installed as devDependencies with **no** test runner
(`vitest`/`jest`) to use them.

### Requested change

1. Add `"test": "playwright test"` and, if unit coverage is wanted, a `vitest` setup that justifies the `jsdom` dependency.
2. Add a CI job: `npx playwright install --with-deps && npm test`.
3. Either use `jsdom` or remove it.

---

## IR-008 · MEDIUM · Unfixable CVE in `ecdsa`, pulled in by `python-jose`

**Owner:** Master Prompt 03 — Security & Privacy
**Blocker ID:** B-8

### Evidence

```
$ cd backend && .venv/bin/pip-audit -r requirements.txt
Found 1 known vulnerability in 1 package
Name  Version ID              Fix Versions
----- ------- --------------- ------------
ecdsa 0.19.2  PYSEC-2026-1325
```

`Fix Versions` is empty — **there is no patched release**. `ecdsa` is a transitive
dependency of `python-jose[cryptography]>=3.3` (`backend/requirements.txt:16`).
The project signs JWTs with **HS256** (`config.JWT_ALGORITHM`), so no ECDSA code
path is used at runtime — but the vulnerable package is still installed and shipped.

### Requested change

Assess migrating from `python-jose` to `pyjwt[crypto]`, which does not depend on
`ecdsa`. HS256 encode/decode is a near drop-in. If the migration is rejected,
record a documented risk acceptance with the reasoning above.

---

## IR-009 · MEDIUM · Python dependencies are not locked

**Owner:** Master Prompt 07 — Infrastructure
**Blocker ID:** B-9 · Detail: `docs/REPRODUCIBILITY.md` §4

All 20 direct dependencies in `backend/requirements.txt` use `>=` with no upper
bound and no lock file, so two installs at different times can resolve differently.
The frontend does this correctly via `package-lock.json` + `npm ci`.

The exact tree behind this audit's "97 passed" is preserved at
`docs/agent-reports/baseline-release-evidence/20-backend-pip-freeze.txt` (87 packages).

**Requested:** add a generated `backend/requirements.lock.txt` and install from it
in `backend/Dockerfile` and CI. `backend/requirements.txt` is a package manifest —
explicitly outside this stage's scope.

---

## IR-010 · LOW · Version metadata is inconsistent and unmaintained

**Owner:** Master Prompt 10 — Integration & Release Manager
**Blocker ID:** B-12 · Detail: `docs/ROLLBACK_AND_VERSIONING.md` §2

- `backend/pyproject.toml` → `version = "1.0.0"`
- `frontend/package.json` → `version = "0.0.0"`
- `openapi.json` → `Smart Decor 1.0.0`
- Repository tags: **none**
- `CHANGELOG.md`: **absent**

**Requested:** adopt the SemVer policy in `docs/ROLLBACK_AND_VERSIONING.md`, tag
`v1.2.0-baseline` on `f97bfad`, align both version fields, and start a CHANGELOG.

---

## IR-011 · MEDIUM · Rollback is not currently executable

**Owner:** Master Prompt 07 — Infrastructure
**Detail:** `docs/ROLLBACK_AND_VERSIONING.md` §4.2

1. Container images float (`ankane/pgvector:latest`, `redis:7-alpine`, `caddy:2-alpine`) — "the previous image" is not identifiable. Pin by digest.
2. No backup schedule is implemented; `docs/DEPLOYMENT.md` §1 only advises "scheduled `pg_dump` backups". Implement it and state the RPO.
3. `alembic downgrade` has never been exercised, and `0003`'s `downgrade()` uses `op.drop_constraint`, which SQLite also rejects (see IR-002).

Without these three, the runbook in `docs/ROLLBACK_AND_VERSIONING.md` §4.3 cannot
be executed as written.

---

## Summary

| ID | Severity | Owner | Title |
|---|---|---|---|
| IR-001 | Critical | 03 | Demo accounts seeded in production |
| IR-002 | High | 04 / 07 | ruff CI failure + SQLite-hostile migration `0003` |
| IR-003 | High | 07 / 04 / 08 / 02 | Stale test counts and dangling file references |
| IR-004 | Medium | 06 / 07 | Eight declared-but-unread env variables |
| IR-005 | Medium | 07 | CSP `img-src` host mismatch |
| IR-006 | High | 07 | CI has never run |
| IR-007 | High | 08 | No executable frontend test path |
| IR-008 | Medium | 03 | Unfixable `ecdsa` CVE via `python-jose` |
| IR-009 | Medium | 07 | Python dependencies not locked |
| IR-010 | Low | 10 | Inconsistent version metadata, no tags, no CHANGELOG |
| IR-011 | Medium | 07 | Rollback not executable (floating images, no backups, untested downgrade) |
