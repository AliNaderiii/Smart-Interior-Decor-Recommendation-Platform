# Backup, Restore & Rollback — Disaster Recovery Runbook

Owner: Stage 07 (Infrastructure / Database Reliability). This document is the
operational counterpart of `docs/DEPLOYMENT.md`. **Read it before the first
production deploy, not after the first incident.**

---

## 1. What must be backed up

| Asset | How | Frequency | Notes |
|---|---|---|---|
| `postgres` volume (pgdata) | `pg_dump` (logical) **and** provider snapshots (physical) | logical: daily; snapshot: provider SLO | The database is the only state that cannot be rebuilt — users, projects, moodboards, feedback, audit trail. |
| `redis` volume (redisdata) | **Not backed up** | — | Redis is a cache + short-lived throttle/blacklist state. Losing it logs everyone out and resets rate limits — acceptable, and safer than restoring stale blacklist state. |
| Object storage (S3) | provider replication / versioning | provider SLO | Enable bucket versioning; media objects are immutable by key (UUID). |
| `.env` secrets | secret manager / encrypted vault | on change | Losing `.env` = losing the Fernet key = **ciphertext at rest becomes unrecoverable** (Stage 03 T-45). Store a copy of `FERNET_KEY` + `SECRET_KEY` outside the server. |

**Restore objective.** The platform's rollback SLO (see
`docs/ROLLBACK_AND_VERSIONING.md` §4.2) is **RTO ≤ 60 min, RPO ≤ 24 h** for a
single-region VPS deployment with daily logical backups. A managed-Postgres
provider (Liara/Arvan RDS-style) with PITR improves RPO to minutes — choose it
for the production contract.

---

## 2. Backup procedures

### 2.1 Logical backup (pg_dump) — the one you can restore anywhere

```bash
# On the deploy host (or via the postgres container):
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
  > backups/decor-$(date -u +%Y%m%dT%H%MZ).dump

# Plain SQL variant (portable across PG majors):
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=plain \
  > backups/decor-$(date -u +%Y%m%dT%H%MZ).sql
```

Schedule (cron on the host, or a `backup` one-shot service in the compose
overlay):

```cron
15 2 * * *  cd /opt/decor && ./scripts/backup.sh >> backups/backup.log 2>&1
```

`scripts/backup.sh` (provided by this stage):

```bash
#!/usr/bin/env bash
# One-shot logical backup with retention (keep 14 daily, 8 weekly).
set -euo pipefail
STAMP=$(date -u +%Y%m%dT%H%MZ)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "${POSTGRES_USER:?}" -d "${POSTGRES_DB:-decor}" --format=custom \
  > "backups/decor-${STAMP}.dump"
find backups -name 'decor-*.dump' -mtime +14 -delete
echo "backup complete: backups/decor-${STAMP}.dump"
```

**Off-site rule:** copy the dump to object storage nightly
(`aws s3 cp backups/ s3://decor-backups/ --recursive` with the same S3
credentials pattern). A backup on the same disk as the database is a receipt,
not a backup.

### 2.2 Physical snapshot

Provider-level volume snapshot of the `pgdata` volume (Arvan/Liara/AWS
volume snapshots) — the fast path for same-region restores. Keep at least the
last 3.

### 2.3 Verification (mandatory)

Restores are tested in CI-style environments and **quarterly from the actual
backups**:

```bash
# restore into a throwaway container (never the live cluster):
docker run --rm -v decor_pgdata:/var/lib/postgresql/data -e POSTGRES_USER=... \
  ankane/pgvector:v0.6.2-pg16 pg_restore --list backups/decor-XXXX.dump | head
```

Full restore drill: see §3. Every drill records RTO. Evidence from the last
drill lives in `docs/agent-reports/infra-evidence/` (when run).

---

## 3. Restore procedure (RTO ≤ 60 min target)

```bash
# 1. STOP traffic (read-only mode or scale backend to 0):
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop backend
# 2. Replace the data volume with a fresh one:
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
docker volume rm decor_pgdata   # ONLY after confirming the backup file is readable
# 3. Start just Postgres and restore:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists \
  < backups/decor-20260821T0200Z.dump
# 4. Boot everything and verify:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
curl -fsS https://yourdomain/api/v1/health/ready        # expect 200
curl -fsS https://yourdomain/api/v1/health | grep -q '"status":"ok"'
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM users;"
```

**Post-restore checks (Stage 03 boot guard is your friend):** if the dump was
taken from a staging/development environment, the backend will REFUSE to start
when a demo account exists in the restored database
(`REFUSE_DEMO_ACCOUNTS_IN_PRODUCTION`, `assert_no_demo_accounts_in_production`).
That is the guard doing its job — delete/rename those rows and rotate anything
they touched before serving traffic (`docs/security/DEMO_ACCOUNTS.md` §runbook).

---

## 4. Rollback of a release (zero-downtime where possible)

Two kinds of rollback — know which one you need:

### 4.1 Code-only rollback (no schema change) — preferred path

1. The CI `docker` job tags images with the git SHA and `latest` on
   `v2-strict-mode`/`main`. Every release is therefore an identifiable image.
2. Rollback = redeploy the previous image:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  up -d --no-deps backend=ghcr.io/<org>/backend:<previous-sha>
```

Because migrations are additive (new columns/tables only), an old image can
run against the new schema for the window you need — **if** the release added
no destructive migration (see the rule below).

### 4.2 Schema rollback (downgrade migration)

Migrations are versioned with reversible `downgrade()` (verified in CI:
`upgrade head → downgrade base → upgrade head`). To roll back a schema:

```bash
# Identify the release's head revision from the release notes, then:
docker compose ... exec backend alembic downgrade -1     # or a named revision
docker compose ... exec backend alembic current
```

**Rules that keep rollback executable (IR-011):**

1. Images are version-pinned (`python:3.12.9-slim`, `node:22.14-alpine`,
   `nginx:1.27.4-alpine`, `ankane/pgvector:v0.6.2-pg16`, `redis:7.4-alpine`,
   `caddy:2.8-alpine`) — "the previous image" is always identifiable. Digest
   pinning is the documented next hardening step (§6).
2. Never ship a destructive migration (DROP COLUMN / table rewrite) in the
   same release as the code that stops writing the dropped data: drop the
   column one release later, after the rollback window has passed.
3. `alembic downgrade` is exercised in CI on every PR (round-trip job).
4. A restore from backup (§3) is always the fallback if the schema path is
   not reversible.

### 4.3 Decision matrix

| Situation | Action | RTO |
|---|---|---|
| Bad code, schema unchanged | redeploy previous image (§4.1) | minutes |
| Bad code + additive schema | redeploy previous image (old code tolerates new schema) | minutes |
| Bad code + destructive schema | `alembic downgrade -1` then previous image (§4.2) | < 1 h |
| Data corruption / deletion | restore from backup (§3) | ≤ 60 min target |
| Secret rotation | `SECRET_KEY`/`FERNET_KEY` rotation runbook (`docs/ROLLBACK_AND_VERSIONING.md` §4.4) | minutes |

---

## 5. Incident response order

1. **Readiness probe** (`/api/v1/health/ready`) — the LB already stopped
   traffic if it is red; do not fight the LB.
2. **Correlate** — pull logs by `X-Request-ID`; check `redis_up` and
   `http_requests_total{status="5xx"}` on `/metrics`.
3. **Decide** — code rollback (§4.1) is faster than restore; restore (§3)
   only for data problems.
4. **Act**, then **verify** (readiness 200 + smoke login + `SELECT count(*)`).
5. **Record** — update `docs/agent-reports/infra-report.md` and the risk
   register; rerun a restore drill if the incident was a restore.

---

## 6. Remaining hardening (documented, not yet done)

| Item | Why | Who can close |
|---|---|---|
| Pin base images by **digest** (`@sha256:…`) | version tags can be re-pointed; digests cannot | run the `docker pull && docker inspect --format '{{index .RepoDigests 0}}'` commands on a networked machine and update the Dockerfiles/compose |
| Managed Postgres with PITR | RPO drops from 24 h to minutes | cloud provider / client decision |
| Restore drill against real backups | the only way to believe an RTO | quarterly ops task |
| WAF / DDoS edge | out of repo scope (risk O-01) | platform provider |
