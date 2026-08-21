# Stage 07 — Production Infrastructure, CI/CD & Observability Report

Date: 2026-08-21 (sandbox execution timestamps are UTC)
Repository: `AliNaderiii/Smart-Interior-Decor-Recommendation-Platform`
Branch: `arena/01a0252d-smart-interior-decor-recommend`
Base commit: `7f424f08659d10ca7923e3dc548da6ae355044a7`

## Decision

**CONDITIONAL PASS.** The repository implementation, local backend/frontend gates,
real PostgreSQL/pgvector + Redis checks, migration round trip, observability
smoke, security probes, and multi-worker verification pass on the sandbox
processes described below. The decision is conditional because no real GitHub
Actions run has been observed and this sandbox has no Docker runtime, hadolint,
Trivy, or Chrome. Those checks are not inferred from local results.

## Evidence boundary

Evidence is classified deliberately:

- **LOCAL** — commands run in this sandbox against real child processes or
  installed package tooling. PostgreSQL is `pgserver`'s embedded PostgreSQL
  16.2 with pgvector 0.6.2; Redis is `redislite` 6.2.14 listening on
  `127.0.0.1:6399`. These are real PostgreSQL/Redis protocol servers, but they
  are not Docker containers.
- **SANDBOX STRUCTURAL** — YAML/text checks that do not execute Docker or a
  GitHub runner.
- **GITHUB ACTIONS** — **BLOCKED / no run URL**. The complete workflow is
  versioned at `ci/github-ci.yml`, but it is not installed under
  `.github/workflows/` in this branch because the configured GitHub App lacks
  workflow-file permission.
- **STAGING / PRODUCTION** — not run. No claim below is a staging or production
  deployment result.

Verbatim or curated command transcripts are in
`docs/agent-reports/infra-evidence/`.

## Incident and recovery disclosure

An earlier pass accidentally ran `git reset --hard HEAD~1` after a temporary
workflow-permission probe. That removed uncommitted tracked-file changes. The
probe push was rejected, and the exact first-hand rejection is preserved in
`infra-evidence/00-git-push-permission-test.log`:

```text
refusing to allow a GitHub App to create or update workflow
.github/workflows/_perm_test.yml without `workflows` permission
error: failed to push some refs
```

No second destructive Git operation was used. `git fsck` was inspection only and
found no recoverable copies of the lost edits beyond temporary probe objects.
The lost files were reconstructed from the committed baseline, surviving
untracked files, prior evidence, and the Stage 07 requirements. The complete
account of lost versus surviving/reconstructed work is
`docs/agent-reports/infra-recovery-note.md`. A reconstructed file is not called
byte-for-byte identical to the lost version; it is called passing only after a
new test or validation supports that statement.

## Implemented repository changes

### CI/CD

`ci/github-ci.yml` is a complete PR/push workflow with these jobs:

- `backend`: PostgreSQL 16 + pgvector service, real Redis service, lockfile
  install, empty-database migration, downgrade/re-upgrade, 400-test backend
  suite, ruff, pip-audit, Stage 03 probes, and deterministic mock extraction
  benchmark. REAL Gemini mode runs only when the `GEMINI_API_KEY` secret exists
  and otherwise emits a skip warning.
- `multi-worker`: two real API processes sharing the service Redis, checking
  blacklist, brute-force lockout, and rate-limit state.
- `frontend`: `npm ci`, oxlint, strict typecheck, the existing node:test unit
  glob, production build, npm audit, and a credential-pattern scan before the
  `frontend-dist` artifact upload.
- `security-scans`: repository secret scan, documentation-link scan, and dead
  translation-key scan.
- `docker`: four `docker compose config -q` checks plus backend and frontend
  BuildKit builds.
- `lighthouse`: budget-gated Lighthouse run and a credential-pattern scan
  before report upload.

`scripts/enable_ci.sh` installs `ci/github-ci.yml` as
`.github/workflows/ci.yml`, commits only that path, and pushes the current
branch. It refuses unrelated staged paths and never force-pushes. A repository
owner/maintainer with workflow permission must run it from a normal clone:

```bash
mkdir -p .github/workflows
cp ci/github-ci.yml .github/workflows/ci.yml
./scripts/enable_ci.sh
```

Afterwards, a real run must be observed and branch protection configured. Until
then, CI is **BLOCKED**, not active.

### Containers and compose

- Backend is a two-stage, lockfile-pinned `python:3.12.9-slim` build and runs
  as non-root `appuser`.
- Frontend is a Node 22.14 build plus nginx 1.27.4 runtime with SPA fallback,
  security headers, proxy forwarding, and no Node toolchain in the runtime.
- Base compose uses `ankane/pgvector:v0.6.2-pg16`, `redis:7.4-alpine`, and
  `caddy:2.8-alpine`; backend has a database+Redis readiness healthcheck.
- `docker-compose.dev.yml` is explicitly development-shaped and is the only
  profile that enables `SEED_DEMO_ACCOUNTS=true`.
- `docker-compose.prod.yml` sets `APP_ENV=production`, JSON logs, resource
  limits, and a daily maintenance loop for audit retention.
- `docker-compose.test.yml` wires `TEST_REDIS_URL=redis://redis:6379/9` and
  the real-Postgres/real-Redis test profile.
- The base product loader is idempotent (`--if-empty`, `--from-json`) and does
  not pass `--seed-demo-accounts`; production configuration validation also
  refuses the flag and refuses predictable demo rows at startup.

### Database, dependencies, and rollback

- `backend/requirements.lock.txt` is the generated install source for CI and
  Docker. The PyJWT migration removes `python-jose` and its `ecdsa` dependency.
- Alembic revision `0003_product_feedback` uses batch mode for the unique
  constraint, making the migration path work on SQLite and PostgreSQL.
- `scripts/backup.sh` performs a custom-format `pg_dump` with 14-day local
  retention. `docs/DISASTER_RECOVERY.md` documents off-site copies, restore,
  release rollback, migration rollback rules, RTO and RPO.
- The documented single-region target is **RTO ≤ 60 minutes** and **RPO ≤ 24
  hours** with daily logical dumps. Managed PostgreSQL PITR can improve RPO;
  neither PITR nor a real-backup restore drill was executed in this sandbox.
- `backend/scripts/prune_audit_logs.py` supports configured retention, dry-run,
  one-transaction deletion and row-count logging. The production overlay runs
  it daily; the 180-day policy value still needs privacy-owner confirmation.

### Observability

- `RequestIDMiddleware` validates/limits inbound `X-Request-ID`, generates one
  when absent or hostile, echoes it, and makes it available through a
  `contextvars` record factory.
- `JSONFormatter` and structured logging are enabled with `LOG_FORMAT=json`;
  redaction runs at both record creation and formatter boundaries. JWTs,
  bearer credentials, secret query values, PANs, and emails are not emitted as
  raw values.
- `MetricsMiddleware` exposes bounded counters, latency histograms, in-flight
  gauge, `redis_up`, and `app_info` through bare `/metrics`; the scrape path is
  excluded from request counters.
- `/api/v1/health` is liveness. `/api/v1/health/ready` checks `SELECT 1` and
  Redis `PING` and returns 503 with per-dependency details when not ready.
- Caddy and FastAPI CSP copies are aligned to the documented Arvan `ir-thr-at1`
  endpoint; Caddy also routes `/metrics` to the backend.

## LOCAL verification results

| Gate | Exact command / environment | Result |
|---|---|---|
| SQLite backend suite | `cd backend && /tmp/infra-venv/bin/pytest tests/ -v --tb=short` with SQLite + fakeredis defaults | **392 passed, 8 skipped**, exit 0; PyJWT auth/security paths included |
| PostgreSQL migration | `alembic downgrade base`, `alembic upgrade head`, round trip again; PG 16.2 + pgvector 0.6.2 | **PASS**, head `0003`, vector extension 0.6.2, HNSW index `ix_products_style_embedding` |
| PG/pgvector + real Redis suite | `DATABASE_URL=.../tmp/pgdata-infra`, `REDIS_URL=redis://127.0.0.1:6399/1`, `TEST_REDIS_URL=.../9`; `pytest tests/ -v --tb=short` | **400 passed**, 5 deprecation warnings, exit 0 |
| Real Redis semantics | `tests/test_redis_real.py` under `TEST_REDIS_URL` | **8 passed** as part of the 400 |
| Multi-worker shared Redis | `python scripts/verify_multi_worker_redis.py`, two uvicorn processes, real Redis | **3/3 passed**: blacklist, lockout, rate limit |
| Negative multi-worker control | same script with `REDIS_URL=` | **0/3 passed, expected exit 1**; wrapper verified the failure, proving fakeredis is not incorrectly accepted |
| Demo seeding | `python ../docs/security/probes/probe_demo_seeding.py` | **0 production runs created demo accounts**; development opt-in created 3 as intended |
| Production fail-safe probe | `python ../docs/security/probes/probe_production_failsafe.py` | **8 checks, 8 secure, 0 INSECURE** |
| API security probe | `PROBE_REDIS_URL=.../15 PROBE_DB_URL=.../tmp/pgdata-infra python docs/security/probes/probe_api_security.py` | **37 checks, 37 secure, 0 INSECURE** |
| Observability live smoke | 2-worker uvicorn on `0.0.0.0:8200`, JSON logs, real PG/Redis; curl liveness/readiness/request-id/metrics/register/login | **PASS**; readiness DB+Redis ok, supplied and generated request IDs echoed, `redis_up 1`, register 201, login 200 |
| Ruff | `cd backend && /tmp/infra-venv/bin/ruff check app ai scripts tests` | **All checks passed** |
| Python dependency audit | `/tmp/infra-venv/bin/pip-audit -r backend/requirements.txt` | **No known vulnerabilities found**, exit 0 |
| Secret/hygiene scan | `/tmp/infra-venv/bin/python scripts/audit_secrets.py` | **0 findings, 0 forbidden paths**, PASS |
| Frontend | `npm ci`, `npm run lint`, `npx tsc -b`, `node --experimental-strip-types --test tests/unit/*.test.ts`, `npm run build`, `npm audit --audit-level=low` | **PASS**; 12 lint warnings/0 errors, 9 unit tests pass, 0 audit vulnerabilities, dist credential hits 0 |
| Translation-key scan | `npx tsx scripts/auditDeadKeys.ts` | **0 DEAD, 0 PARTIAL**, PASS |
| Compose/workflow structure | PyYAML structural validator over all four compose files and workflow | **PASS**; no floating `latest`, base has healthcheck/no demo flag, expected six jobs |

## Security and dependency notes

The reconstructed PyJWT migration was validated by the full auth/security suite,
the forged-role JWT test, lock installation, `pip check`, and `pip-audit`. The
lock verification observed:

```text
No broken requirements found.
WARNING: Package(s) not found: ecdsa, python-jose
PyJWT 2.13.0
64 pinned lock entries
```

The short HMAC key used by the existing SQLite test fixture produces PyJWT's
non-blocking `InsecureKeyLengthWarning`; production validation requires a key
of at least 32 characters. No secret or PII is placed in the frontend build
artifact; test fixtures are acknowledged explicitly by the repository scanner
as generated test-only credentials.

## BLOCKED checks and unblock paths

The following are not passes:

1. **GitHub Actions activation / run URL:** `git push` of a temporary workflow
   was rejected with the exact `without workflows permission` message in
   `00-git-push-permission-test.log`. No Actions run URL exists. Unblock by
   having a maintainer with the `workflows`/`workflow` permission run
   `scripts/enable_ci.sh`, then record the Actions run URL and status.
2. **Docker Compose config and image builds:**
   `docker compose config -q` and `docker build ...` were attempted as
   environment checks and returned `/bin/bash: docker: command not found`
   (exit 127). Unblock on a Docker-enabled runner; the GitHub `docker` job also
   runs the two image builds. Hadolint and Trivy were not installed (`command
   not found`), so no local lint/image-scan result is claimed.
3. **Lighthouse/Chrome:** `google-chrome --version` and `chromium --version`
   returned `command not found` (exit 127). Unblock on the GitHub Lighthouse
   runner or a machine with headless Chrome.
4. **REAL Gemini extraction benchmark:** `GEMINI_API_KEY` is empty in this
   sandbox. The mock benchmark is the deterministic CI baseline; real-mode
   quality is not claimed. Unblock by configuring the repository secret and
   reviewing provider egress/cost controls.
5. **Production/staging deployment:** no staging or production deployment,
   live backup/restore drill, managed-PG PITR, digest pinning, branch
   protection, or real release rollback occurred in this sandbox.

## Integration requests

The resolution record is appended to `integration-request.md`.

- Completed in this branch: IR-SEC-001, IR-SEC-002/IR-008, IR-SEC-007 (with
  privacy-owner confirmation pending), IR-002, IR-003 for Stage 07 scope,
  IR-005, IR-009, and IR-011 with digest/restore residuals.
- Implemented but externally blocked: IR-SEC-006 / IR-006 (workflow activation).
- Delegated unchanged: IR-SEC-003 to Stage 05; IR-SEC-004/IR-007 to Stage 08;
  IR-SEC-005 to the product/privacy decision; IR-004/IR-010 to their owners.

## Commit sequence

These are the logical checkpoint commits made before the remaining docs/evidence
checkpoint:

- `f212fa9` — recovery/safety note
- `8275d74` — request IDs, readiness, metrics, structured logging
- `b7afd96` — container builds, compose base/test, lockfile, batch migration
- `3133f24` — PyJWT dependency migration
- `ca1ede6` — audit retention script/tests/production maintenance
- `3efa8af` — multi-worker Redis verifier and development compose overlay
- `0ba3df4` — PyJWT forged-role test fixture
- `6cd1fb9` — ruff import normalization

The final docs/evidence checkpoint will be listed here after it is committed.

## Reproduction pointers

See `docs/agent-reports/infra-evidence/README.md` for the evidence index and
`docs/DISASTER_RECOVERY.md` for operational recovery. Do not treat the existence
of a workflow definition as evidence that GitHub Actions has run.

## Final tracked-tree scan after evidence commit

After committing the report and evidence, the scans were rerun against the
tracked tree at `ca573ba`:

- `scripts/audit_secrets.py`: 310 tracked files, 0 findings, 0 forbidden paths,
  PASS.
- `scripts/audit_docs_links.py`: 38 Markdown files, 0 broken links, 0 missing
  file references, PASS.
- `ruff check app ai scripts tests`: all checks passed.
- `pip-audit -r backend/requirements.txt`: no known vulnerabilities.

This final scan transcript is `infra-evidence/07-scans.log`.
