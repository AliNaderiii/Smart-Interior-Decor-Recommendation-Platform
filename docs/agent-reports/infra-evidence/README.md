# Infra / CI-CD / Observability — evidence index (Stage 07)

Files are verbatim or explicitly curated transcripts of the commands in `docs/agent-reports/infra-report.md`; curated logs identify omitted fixture credentials.
Evidence class: **LOCAL** (real processes in the sandbox — PostgreSQL 16.2 +
pgvector 0.6.2 via pgserver, Redis 6.2.14 via redislite). GitHub Actions
activation is **BLOCKED** by the agent token's missing `workflows` permission —
the exact error is in the report (§CI activation) and in `00-git-push-permission-test.log`.

| File | Contents |
|---|---|
| `00-git-push-permission-test.log` | The exact `git push` rejection for a `.github/workflows/` file |
| `01-pg16-migrations-roundtrip.log` | `alembic upgrade head` on a **fresh** Postgres 16.2 + pgvector 0.6.2, then `downgrade base`, then `upgrade head` |
| `02-pg16-pgvector-redis-parity-suite.log` | Full pytest suite vs real Postgres 16.2 + pgvector + **real shared Redis** — `400 passed` (exit 0) |
| `03-probe-demo-seeding.log` | Stage 03 probe — production runs create **0** demo accounts |
| `04-probe-production-failsafe.log` | Stage 03 probe — `8 checks, 8 secure, 0 INSECURE` |
| `05-probe-api-security.log` | Stage 03 black-box probe vs real PG + real Redis — `37 checks, 37 secure, 0 INSECURE` |
| `06-live-observability-smoke.log` | 2-worker uvicorn vs real PG/Redis: liveness, readiness, X-Request-ID echo, login, `/metrics` |
| `07-scans.log` | ruff · pip-audit (`No known vulnerabilities found`) · `audit_secrets.py` PASS · `audit_docs_links.py` |
| `08-frontend-verification.log` | `npm ci` · oxlint 0 errors · `tsc -b` · 9 unit tests pass · build · `npm audit` 0 · dist credential scan 0 |
| `09-multi-worker-shared-redis.log` | Real Redis: `3/3 checks passed` (blacklist, lockout, rate limit shared across two uvicorn workers) |
| `10-multi-worker-fakeredis-negative.log` | Same test, empty `REDIS_URL` (per-process fakeredis): `0/3` — proves the test has teeth and why production refuses fakeredis |
| `11-requirements-lock-verify.log` | Clean-venv lock install — `pip check` clean, 64 pinned lock entries, no `ecdsa`/`python-jose` |
| `12-compose-structure-validation.log` | YAML + structural validation of all four compose files (services, healthchecks, no `latest`, no seeding in base) — **not** Docker Compose execution |
| `13-post-reconstruction-parity.log` | Post-reconstruction full PostgreSQL/pgvector + real Redis suite — `400 passed`, exit 0 |
| `14-blocked-environment-checks.log` | First-hand sandbox `command not found` results for Docker, hadolint, Trivy, Chrome, plus empty Gemini secret state |

The exact `docker compose config -q` and image-build/Trivy results belong to a
**real GitHub Actions runner** (docker job in `ci/github-ci.yml`) — not
reproducible in this sandbox because the Docker runtime is not installed; that is
stated, not simulated.
