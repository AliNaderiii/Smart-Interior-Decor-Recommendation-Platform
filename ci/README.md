# CI workflow

> **Stage 1 (2026-08-26): the workflow to activate is `ci/ci.stage1.yml`.**
> It is a byte-identical copy of `.github/workflows/ci.yml` as of the Stage-1
> work (sha256 `dfdaddfb…59ea43`), staged here as a *regular file* because the
> agent's GitHub App token is refused on any push that creates or updates a
> file under `.github/workflows/` (blocker **B-2 / IR-S1-009**). Everything
> else in Stage 1 pushed normally; only the workflow content had to travel
> this way.
>
> Activate it from a clone whose credentials carry the **`workflows`** scope:
>
> ```bash
> cp ci/ci.stage1.yml .github/workflows/ci.yml
> git add .github/workflows/ci.yml
> git commit -m "ci: activate the Stage 1 workflow"
> git push
> ```
>
> It adds a 7th job, **`e2e`** (Playwright, 29 tests across 4 role-scoped
> projects — the suite has never executed in a browser, see IR-S1-001), and
> moves every Python install onto `backend/requirements.lock.txt` with a
> lock-verification step and a `pip-audit` gate. The job table below predates
> Stage 1 and describes `github-ci.yml`; `ci.stage1.yml` supersedes it.

The canonical workflow is `ci/github-ci.yml`. GitHub blocked the agent App
token from pushing workflow files (verified 2026-08-21 — the exact error is in
`docs/agent-reports/infra-report.md`, section "CI activation: BLOCKED"), so
the file lives here and is installed into the canonical GitHub location by
`scripts/enable_ci.sh` from a clone authenticated with a token that has the
**`workflows`** scope.

Jobs (each gate is blocking):

| Job | Gate |
|---|---|
| `backend` | pytest vs **Postgres 16 + pgvector + Redis** service containers, `alembic upgrade head` from empty DB, ruff, pip-audit, migration round-trip (upgrade → downgrade base → upgrade), backend probes (demo-seeding + production failsafe) |
| `frontend` | `npm ci`, oxlint (0 errors), `tsc -b` strict typecheck, unit tests (`node --experimental-strip-types --test tests/unit/*.test.ts` — the documented vitest workaround until IR-SEC-004 lands), production build, `npm audit` |
| `multi-worker` | real uvicorn workers sharing one Redis — blacklist, lockout and rate limits shared (`scripts/verify_multi_worker_redis.py`) |
| `security-scans` | `scripts/audit_secrets.py` (no unacknowledged findings), `scripts/audit_docs_links.py`, `pip-audit`, `npm audit` |
| `docker` | `docker compose config -q` + `docker build` of both images (gate; requires the `docker` runner) |
| `lighthouse` | performance ≥ 80, LCP < 3 s on the SPA (Chrome on the runner) |

Artifacts: `frontend/dist` and `lighthouse-report.json` — both post-scanned
for credential patterns before upload (an artifact containing a secret fails
the job).
