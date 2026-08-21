# Rollback & Versioning Strategy

Baseline: `f97bfad` · Owner: Baseline & Release Governance (Master Prompt 01).
Execution of the tagging commands below is **recommended, not performed** — this
agent is scoped to documentation/metadata and must not mutate shared refs.

---

## 1. Current state

| Fact | Value |
|---|---|
| Tags in the repository | **8**, all ad-hoc milestone names, none SemVer, none on the baseline: `v1.1-final-p0p1-fixed` (`a847ad5`), `v2-phase0-audit-complete`, `v2-phase2-performance`, `v2-phase3-ui`, `v2-phase4-deadkeys`, `v2-final` (`dd2c34d`), `v2-datasets-realistic`, `v2-datasets-realistic-merged` (`939e05c`) |
| GitHub Releases published | **0** — no tag has release notes |
| `CHANGELOG.md` | **absent** |
| GitHub default branch | `main` |
| Authoritative development branch | `v2-strict-mode` |
| `main` vs `v2-strict-mode` | `main` = `0998ba4`, `v2-strict-mode` = `f97bfad` → **`main` is 7 commits behind** |
| Backend version declared | `backend/pyproject.toml` → `version = "1.0.0"` |
| Frontend version declared | `frontend/package.json` → `version = "0.0.0"` (never maintained) |
| Version reported by the API | `openapi.json` → `Smart Decor 1.0.0` |

Consequences today: the newest tag (`v2-datasets-realistic-merged`, `939e05c`) is
**4 commits behind the baseline**, so **`f97bfad` has no immutable reference of its
own**; the tag names carry no ordering or compatibility semantics (`v2-final` is
not the final v2 commit — `f97bfad` is); no tag has release notes; the two version
declarations disagree; and a contributor who clones the default branch receives a
tree that is 7 commits stale.

---

## 2. Versioning policy (proposed)

Semantic Versioning 2.0.0 applied to the **product as a whole**, with backend and
frontend versions kept in lockstep.

| Component | SemVer meaning for this product |
|---|---|
| **MAJOR** | Breaking API contract change, a migration that cannot be downgraded, or a change to the auth/session model |
| **MINOR** | New endpoint, new portal capability, new recommender stage, new provider adapter — backward compatible |
| **PATCH** | Bug fix, documentation, dependency bump, CI change — no contract change |

Pre-release qualifiers: `-baseline`, `-rc.N`, `-staging.N`.
Build metadata is not used; the commit SHA is recorded in the release notes.

### 2.1 Version derivation for the current tree

`1.0.0` (declared) predates the V2 strict-mode work (security hardening, feedback
API, perf rework, UI rebuild) and the V3 dataset integration. The existing tag
`v1.1-final-p0p1-fixed` marks the 1.1 line at `a847ad5`, which is consistent with
`1.0.0` + one MINOR. Since then V2 added endpoints (`/feedback` ×3) and V3 added
the dataset pipeline, backward compatibly → **one further MINOR**.

The existing tags should be kept as historical markers and **not** renamed;
SemVer starts from the baseline forward.

**Recommended baseline tag: `v1.2.0-baseline`** on `f97bfad`.

```bash
# Run by the Release Manager (Prompt 10) on a normally-authenticated clone.
git checkout v2-strict-mode
git pull --ff-only
git rev-parse HEAD    # MUST print f97bfad371c7a33cb4fe9f52b7c51520a363fb43

git tag -a v1.2.0-baseline -m "Baseline: audited release baseline, see docs/RELEASE_BASELINE.md

Verified at this commit: backend 97/97 pytest (SQLite+fakeredis+mock AI),
frontend strict build 0 errors, oxlint 0 errors, secret scan 0 findings.
NOT verified at this commit: Postgres+pgvector parity, real-model AI accuracy,
seller-link liveness, Lighthouse. Open blockers: B-1..B-12."

git push origin v1.2.0-baseline
```

> The tag message deliberately records the *unverified* set. A tag that only
> lists successes is how a stale acceptance report is born.

### 2.2 Version bookkeeping to fix (out of this agent's scope — IR-010)

- `frontend/package.json` `version` must track the product version (currently `0.0.0`).
- `backend/pyproject.toml` `version` must be bumped in the same commit as the tag.
- Add `CHANGELOG.md` in Keep-a-Changelog format; the baseline entry is
  `docs/RELEASE_BASELINE.md` §2.

---

## 3. Branch and release flow

```
feature / agent branch  ──PR──►  v2-strict-mode  ──PR──►  main  ──tag──►  release
   agent/<stage>-<date>            (integration)          (stable)      vX.Y.Z
   arena/<session-id>
```

Rules (from `agent-master-prompts/00-README.md`, enforced by this stage):

1. Agents branch from the baseline commit; they never merge, rebase, reset,
   force-push or cherry-pick another agent's branch.
2. Every agent PR targets `v2-strict-mode`. Only Prompt 10 merges.
3. Only Prompt 10 promotes `v2-strict-mode` → `main` and creates tags.
4. Tags are created on `main` after promotion; `v2-strict-mode` may carry
   `-rc.N` pre-release tags.
5. **Recommended branch protection on `v2-strict-mode` and `main`** (needs C-8):
   require PR review, require status checks `backend`, `frontend`, `lighthouse`,
   forbid force-push, forbid deletion.

---

## 4. Rollback runbook

### 4.1 Rollback decision matrix

| Symptom | Rollback scope | Action |
|---|---|---|
| Frontend regression only | Application | Redeploy the previous frontend image/tag; backend untouched |
| Backend regression, **no** new migration | Application | Redeploy the previous backend image/tag |
| Backend regression **with** a new migration | Application + schema | §4.3 — downgrade then redeploy |
| Data corruption | Data | §4.4 — restore from `pg_dump`; application rollback alone is insufficient |
| Secret leak | Credentials | §4.5 — rotate first, roll back second |

### 4.2 Prerequisites that do not exist yet

Record honestly: **this repository cannot currently execute a clean rollback**, because

- the 8 existing tags are ad-hoc milestone markers with no release notes, none points at the baseline, and no image digest identifies a known-good build (B-12);
- `docker-compose.yml` uses floating tags (`ankane/pgvector:latest`, `caddy:2-alpine`, `redis:7-alpine`) — "the previous image" is not reproducible;
- there is no documented backup schedule, only the advisory line "scheduled `pg_dump` backups" in `docs/DEPLOYMENT.md` §1;
- `alembic downgrade` has never been exercised (and revision `0003`'s `downgrade()` uses `op.drop_constraint`, which SQLite also rejects).

Closing those three gaps is **IR-011** (Prompt 07).

### 4.3 Application + schema rollback (once SemVer tags and pinned images exist)

```bash
# 0. Freeze traffic
docker compose exec caddy caddy stop        # or drain at the load balancer

# 1. Back up BEFORE touching anything
docker compose exec postgres pg_dump -U decor -Fc decor > rollback-$(date -u +%Y%m%dT%H%M%SZ).dump

# 2. Identify the target
git ls-remote --tags origin | sort   # 8 legacy milestone tags + any SemVer tags
TARGET=v1.2.0-baseline

# 3. Downgrade the schema to the target's alembic revision
docker compose exec backend alembic current
docker compose exec backend alembic downgrade <revision-of-$TARGET>

# 4. Redeploy the application at the target
git checkout $TARGET
docker compose up -d --build backend frontend

# 5. Verify
curl -fsS https://<host>/api/v1/health
docker compose exec backend pytest tests/ -q

# 6. Resume traffic
```

### 4.4 Data-only restore

```bash
docker compose stop backend
docker compose exec -T postgres pg_restore -U decor -d decor --clean --if-exists < <backup>.dump
docker compose start backend
```

### 4.5 Credential compromise

Rotate **before** rolling back — a rollback re-deploys the compromised secret otherwise.

| Secret | Rotation | Blast radius |
|---|---|---|
| `SECRET_KEY` | new `openssl rand -hex 32`, restart backend | **All sessions invalidated — by design** |
| `FERNET_KEY` | MultiFernet dual-key window, re-encrypt, then retire the old key | Encrypted fields unreadable if retired too early |
| `POSTGRES_PASSWORD` | `ALTER ROLE`, update `.env`, restart | Backend downtime until both sides match |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` | Revoke at the provider, issue new, restart | AI extraction degrades to mock |
| `ZARINPAL_MERCHANT_ID` | Coordinate with the PSP | Payment outage |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Rotate at the provider | Uploads fail; existing public URLs survive |
| Demo account passwords | **Delete the accounts** (B-1/IR-001) rather than rotate | None |

### 4.6 Rollback SLO (proposed, requires C-2 and IR-011)

| Metric | Target |
|---|---|
| Detection → decision | ≤ 15 min |
| Application-only rollback | ≤ 10 min |
| Application + schema rollback | ≤ 30 min |
| Data restore (150-row demo catalog) | ≤ 15 min |
| Maximum acceptable data loss (RPO) | ≤ 24 h with daily `pg_dump`; ≤ 15 min with WAL archiving |

---

## 5. Ownership matrix

Derived from the `Allowed scope` section of each master prompt. Anyone touching a
path they do not own must instead file an entry in `integration-request.md`.

| Path | Owner (master prompt) |
|---|---|
| `README.md`, `.env.example`, `.gitignore` | **01 — Baseline & Release Governance** |
| `docs/RELEASE_*.md`, `docs/REPRODUCIBILITY.md`, `docs/ROLLBACK_AND_VERSIONING.md` | **01** |
| `docs/agent-reports/baseline-release-*` | **01** |
| `scripts/audit_*.py`, `scripts/check_links.py`, `scripts/enable_ci.sh` | **01** (audit/release tooling) |
| `docs/research/**`, `docs/product/**` | 02 — Research & Benchmark |
| `backend/app/core/**`, `auth.py`, `users.py`, `projects.py`, `moodboards.py`, `docs/security/**` | 03 — Security & Privacy |
| `backend/ai/**`, `backend/app/services/recommender.py`, seed/eval scripts, `docs/ai/**` | 04 — AI, Recommender & Data |
| `frontend/src/**`, frontend assets/styles/build config | 05 — Frontend, RTL & UX |
| `backend/app/services/payment.py`, `storage.py`, `emailer.py`, `link_checker.py` | 06 — Integrations, Payments & Storage |
| `docker-compose*.yml`, `*/Dockerfile`, `frontend/nginx.conf`, `Caddyfile`, `ci/**`, `.github/workflows/**`, deployment docs | 07 — Infrastructure, CI/CD & Observability |
| `backend/tests/**`, `frontend/tests/**`, `docs/qa/**` | 08 — QA & Acceptance Testing |
| `docs/client/**`, `docs/proposal/**`, `docs/demo/**` | 09 — Sales & Demo Documentation |
| Merges, tags, `CHANGELOG.md`, branch protection | 10 — Integration & Release Manager |
| `backend/alembic/**`, `backend/requirements.txt`, `frontend/package.json` | Shared — **integration request required** |
