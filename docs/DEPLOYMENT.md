# Deployment Guide

## 0. One-command local / VPS bring-up

```bash
cp .env.example .env
# fill: SECRET_KEY (openssl rand -hex 32), FERNET_KEY, POSTGRES_PASSWORD,
#       AI_PROVIDER + key, S3_* if using object storage
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Services: `postgres` (PostgreSQL 16 + pgvector), `redis` (Redis 7), `backend`
(runs the migration and an idempotent product-only loader), `frontend` (nginx),
`caddy` (TLS 1.3, ports 80/443). The dev overlay explicitly enables demo
accounts; the base/production profile never passes a demo-seeding flag. App:
`https://<host>/`; interactive API docs are disabled by the application in
production.

## 1. Production checklist

- [ ] `.env`: strong `SECRET_KEY`, `FERNET_KEY`, DB password; `APP_ENV=production`
- [ ] Caddyfile: replace `:443` with your domain → automatic Let's Encrypt,
      remove `tls internal` (keep the `protocols tls1.3 tls1.3` block)
- [ ] `STORAGE_BACKEND=s3` with Arvan/Liara credentials
- [ ] `PAYMENT_PROVIDER=zarinpal` + real `ZARINPAL_MERCHANT_ID` +
      `PAYMENT_CALLBACK_URL=https://yourdomain/upgrade`
- [ ] `AI_PROVIDER=gemini` (or `openai`) with API key; optionally
      `EMBEDDING_BACKEND=clip` (uncomment torch/sentence-transformers in
      `backend/requirements.txt`; first boot downloads ~600 MB)
- [ ] Seed with real CLIP vectors: `python backend/scripts/seed_products.py --real-embeddings`
      (or `--from-json` after copying `backend/seed_data/embeddings_real.json` —
      generated once on a networked machine, intentionally **not committed**;
      see IR-003 — to the deploy host)
- [ ] Validate real extraction quality: `python backend/scripts/evaluate_extraction.py --real --sample 10`
- [ ] Run `python scripts/check_links.py --report docs/reports/links.json` after seeding real catalog
- [ ] Enable CI if not yet active: `./scripts/enable_ci.sh` (needs a token with `workflow` scope)
- [ ] Postgres volume on encrypted disk; schedule `scripts/backup.sh` and copy dumps off-site
- [ ] Confirm `/api/v1/health/ready` is the load-balancer readiness probe; keep `/metrics` private

## 2. Deploy to a VPS / EC2

```bash
ssh user@server
git clone <repo> && cd Smart-Interior-Decor-Recommendation-Platform
cp .env.example .env && $EDITOR .env      # see checklist
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend            # wait for "Application startup complete"
```

Point DNS A-record at the server; Caddy handles certificates automatically.

## 3. Deploy to Liara

1. Create a **PostgreSQL** database (enable `vector` extension from the Liara
   panel or `CREATE EXTENSION vector;`) and a **Redis** instance.
2. Backend: `liara deploy --app decor-api --platform docker` from `backend/`
   (Dockerfile is multi-stage, port 8000). Set env vars from `.env.example`.
3. Frontend: `liara deploy --app decor-web --platform static` after
   `npm run build` (upload `dist/`), or use the frontend Dockerfile.
4. Set `FRONTEND_ORIGIN` on the backend and point the frontend's `/api` proxy
   (Liara "reverse proxy" feature or an edge worker) at `decor-api`.
5. Object storage: create a Liara bucket, set `STORAGE_BACKEND=s3`,
   `S3_ENDPOINT=https://storage.iran.liara.space`, bucket + keys.

## 4. Deploy to ArvanCloud

Same shape: Arvan Managed Postgres (or a pgvector container in Arvan IaaS),
Arvan Object Storage (`S3_ENDPOINT=https://s3.ir-thr-at1.arvanstorage.ir`),
containers via Arvan PaaS or a compute instance running docker-compose.
Put Arvan CDN in front of the frontend for asset caching in-country.

## 5. Migrations

```bash
docker compose exec backend alembic upgrade head      # apply
docker compose exec backend alembic revision --autogenerate -m "…"
```

## 6. Ops runbook

| Symptom | Action |
|---|---|
| `/recommend` slow | check Redis up (`docker compose exec redis redis-cli ping`); verify HNSW index exists (`\di+ ix_products_style_embedding`) |
| pgvector missing | `docker compose exec postgres psql -U decor -c "CREATE EXTENSION IF NOT EXISTS vector"` then re-run migrations |
| dead seller links | `python scripts/check_links.py` (sets `seller_link_ok`, UI shows red dot) |
| rotate JWT secret | change `SECRET_KEY`, restart backend — all sessions invalidated by design |

## 7. Security posture (acceptance criteria mapping)

| Criterion | Where |
|---|---|
| TLS 1.3 all endpoints | `Caddyfile` (`protocols tls1.3 tls1.3`, HTTP→HTTPS redirect, HSTS) |
| bcrypt passwords | `app/core/security.py` (passlib, `$2b$`) |
| Encryption at rest | `KMSClient` Fernet abstraction + provider disk encryption |
| GDPR deletion | `DELETE /api/v1/users/me` hard delete, tested |
| No payment data | `payments` table stores authority/ref_id only |
| JWT 15 min / 7 d + blacklist | `app/core/security.py`, `app/api/routes/auth.py` |
| No secrets in repo | all via `.env`; `.env` gitignored; `.env.example` documented |

## V3: from offline demo to production data

The default Docker seed now loads `backend/seed_data/products_realistic_150.json`. It is realistic **sample structure**, not a live inventory feed.

> **ADR-016 (catalog-integrity gate).** Under `APP_ENV=production` every row of
> the sample catalogs is stamped `source=synthetic-demo` and **excluded from
> recommendations** (`integrity_ok=false`, reason `synthetic_row`). A production
> deployment therefore serves an honest empty catalog until a real seller feed
> is imported; `seed_products.py` refuses to run there at all (exit 0, nothing
> written) unless `--allow-synthetic`. Do not "fix" this by relabelling rows —
> import real inventory.
>
> **Upgrade checklist for an existing database:**
> ```bash
> alembic upgrade head                                   # 0007: provenance + integrity columns (NULL = not yet evaluated)
> python scripts/backfill_integrity.py                   # stamp a verdict on every row (idempotent)
> python scripts/audit_catalog.py --strict               # exit 1 lists what production excludes and why
> python scripts/backfill_integrity.py --unverify-failing   # optional: push failing rows into the admin review queue
> ```
> Until the backfill has run, legacy rows (`integrity_ok IS NULL`) remain
> eligible so the deploy never goes dark. Re-run the backfill whenever
> `INTEGRITY_POLICY_VERSION` changes. `audit_catalog.py --check-images` also
> HEADs every image URL — run it from a machine with egress before a data
> release.
>
> **Expect the legacy synthetic catalog to be excluded wholesale.** Rows written
> by `seed_products.py` before ADR-016 carry template titles («فرش modern») and
> category-blind materials; the backfill marks all of them `title_fa_invalid`
> and/or `material_implausible`, and `/recommend` comes back empty with
> `meta.catalog_quality` explaining why. That is the gate working — replace the
> rows, do not relax the gate. For a **demo/preview** database (`APP_ENV` is
> `development` or `test`) do it once with the corrected sample catalog:
> ```bash
> python scripts/load_realistic_products.py --realistic --expand-to 150 --clear --seed-demo-accounts
> python scripts/backfill_integrity.py
> ```
> `--clear` deletes every product; `feedback_events`, `product_feedback` and
> project items cascade with it (moodboard JSON keeps dangling ids). Fine for a
> demo, never for a customer database — there, import the real feed.
>
> **PaaS without a shell (Render free tier and similar) — ADR-017.** There
> is no console, no pre-deploy hook and, on the free plan, no editable start
> command. So the image prepares itself: `backend/Dockerfile` runs
> `python scripts/entrypoint.py`, which on **every** boot
>
> 1. validates the configuration (`Settings.validate_runtime`),
> 2. runs `alembic upgrade head` (serialised across replicas with a
>    PostgreSQL advisory lock) and refuses to serve unless the database is at
>    head,
> 3. applies `CATALOG_BOOTSTRAP` — `off` (default) · `if-empty` (load the
>    150-row sample catalog only when the table is empty) ·
>    `replace@<label>` (delete every product, reload the sample catalog,
>    **once per label per database** — the label is recorded in
>    `bootstrap_runs`, so redeploys and restarts never wipe twice; pick a new
>    label to do it again),
> 4. creates the demo accounts when `SEED_DEMO_ACCOUNTS=true` (never in
>    production — same gate as always),
> 5. runs the integrity backfill,
>
> and then `exec`s `uvicorn … --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2}`.
>
> **Upgrading a legacy demo database (pre-ADR-016 synthetic rows) from the
> dashboard only:**
>
> | step | Environment | what the next boot does |
> |---|---|---|
> | 1 | `APP_ENV=development`, `SEED_DEMO_ACCOUNTS=true`, `CATALOG_BOOTSTRAP=replace@2026-09-08` | migrates to head, deletes the legacy rows, loads the corrected sample catalog, creates the demo logins, backfills |
> | 2 | change to `CATALOG_BOOTSTRAP=if-empty` | steady state: nothing is deleted again; an accidentally emptied table is repopulated |
>
> Leaving `replace@2026-09-08` in place is safe (the label is spent), but
> `if-empty` states the intent. `APP_ENV=production` refuses any value but
> `off` at boot: the sample catalog is `source=synthetic-demo` and a sold
> deployment imports real inventory. The deploy log shows one `[boot n/5]`
> line per step; `bootstrap_runs` keeps what each replacement deleted.
>
> Rehearse against a copy first:
> ```
> DATABASE_URL=<copy> APP_ENV=development python scripts/entrypoint.py --catalog replace@rehearsal --no-server
> ```
> Compose deployments are unaffected: every compose file still sets an
> explicit `command:` (production = migrations + server, catalog via the
> `catalog-bootstrap` profile job).
>
> Migration `0006` tolerates a `feedback_events` table that `create_all` made
> before Alembic ever ran (the state of a database that was only ever seeded),
> and `0008` does the same for `bootstrap_runs`, so the first real
> `alembic upgrade head` on such a database succeeds instead of crash-looping.

1. Validate the client's export against `datasets/products_realistic.json` and replace the committed/imported catalog through a controlled data release.
2. Set `AI_PROVIDER=gemini` (or `openai`) and provide its key. Keep `EMBEDDING_BACKEND=hash` until CLIP vectors are generated on a networked machine:
   ```bash
   pip install torch sentence-transformers
   python backend/scripts/seed_products.py --real-embeddings
   ```
3. Configure Arvan/Liara/AWS with `STORAGE_BACKEND=s3` and `S3_*`; use licensed product images and a CDN base URL.

### Product-image hosts & CSP (Stage 2, T-2.4 — closes B-11)

The Content-Security-Policy's `img-src` decides which image hosts the browser
will render. **`build_csp()` in `backend/app/core/security_headers.py` is the
single source of truth**; the Caddyfile carries a generated, byte-identical
copy for defence in depth, and `backend/tests/test_csp_alignment.py` fails CI
whenever the two drift (the test also proves every committed catalog
`image_url` origin is allowed — so a catalog/CDN change that would blank the
product images fails before it deploys).

Image origins are derived from, in order:

| Setting | Contributes to `img-src` |
|---|---|
| `S3_PUBLIC_BASE_URL` | its origin |
| `S3_ENDPOINT` | its origin **plus** `https://*.<host>` (virtual-hosted buckets) |
| `IMAGE_CDN_BASE_URL` | its origin — use for a CDN zone in front of the bucket |
| `IMAGE_EXTRA_ORIGINS` | each comma-separated origin (multi-CDN escape hatch) |

`https://images.unsplash.com` is always present: the committed demo catalog
and quiz imagery reference it (documented demo dependency, not a production
requirement).

**After changing any of these settings:**

```bash
# regenerate the proxy copy and paste it into the Caddyfile header block
python backend/scripts/print_csp.py               # your environment
python backend/scripts/print_csp.py --reference   # the committed reference
# verify alignment + catalog coverage
cd backend && python -m pytest tests/test_csp_alignment.py -q
```

4. Set `PAYMENT_PROVIDER=zarinpal`, the merchant ID and HTTPS callback. Card data is never stored; only gateway authority/reference IDs are persisted.
5. Set `EMAIL_PROVIDER=resend`, `RESEND_API_KEY` and a verified `EMAIL_FROM` domain.
6. Generate strong `SECRET_KEY` and `FERNET_KEY`, set production origins/cookies, and store all values in the platform secret manager.
7. Run the loader and checks:
   ```bash
   python backend/scripts/load_realistic_products.py --realistic --expand-to 150 --clear --from-json
   python scripts/check_links.py
   python backend/scripts/audit_catalog.py --strict --check-images   # ADR-016: must be clean for a catalog you intend to sell from
   ```

Without keys, the supported offline path remains mock AI + hash embeddings + local storage + mock payment/email. See `.env.example`, `.env.example.v2`, and `docs/CLIENT_DATASETS_REQUEST.md`.

## 8. Stage 07 production profiles

Use the profiles deliberately; do not use the development overlay for a
production deployment:

```bash
# Local development: host ports, mock providers and explicit demo accounts.
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Production: fail-fast settings, JSON logs, resource limits and daily audit pruning.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

# Postgres/pgvector + real Redis test profile.
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend
```

The base backend command only runs the idempotent realistic **product** loader
when the product table is empty. It does not pass `--seed-demo-accounts`, and
`APP_ENV=production` rejects `SEED_DEMO_ACCOUNTS=true` as a boot-time error.
The dev-only opt-in is isolated in `docker-compose.dev.yml`.

Images are version-pinned in the compose and Dockerfiles: PostgreSQL 16 with
pgvector 0.6.2, Redis 7.4, Caddy 2.8, Python 3.12.9, Node 22.14, and nginx
1.27.4. Digest pinning remains an operator hardening step; record resolved
image digests in the release notes before a high-assurance production rollout.
Python images install `backend/requirements.lock.txt` and run the API as the
non-root `appuser`; the frontend runtime contains only the built static bundle.

## 9. Health, readiness and observability

- `GET /api/v1/health` is liveness and does not prove dependencies are healthy.
- `GET /api/v1/health/ready` is readiness and requires PostgreSQL `SELECT 1`
  plus a shared Redis `PING`. Configure the orchestrator/LB to use it and to
  stop routing on `503`.
- `GET /metrics` is a Prometheus text endpoint. It contains bounded request
  counters, latency histograms, in-flight requests, `redis_up`, and `app_info`;
  it does not include emails, tokens, product ids or request ids. Restrict it
  to the monitoring network at Caddy/firewall level.
- Set `LOG_FORMAT=json` in production. Each JSON line has a timestamp, level,
  logger, request id and event fields; secrets, bearer tokens, JWTs, PANs and
  email addresses are redacted at record creation and formatter output.
- The API accepts a validated `X-Request-ID` and echoes it. Invalid or overly
  long values are replaced, preventing header injection while preserving
  cross-service correlation.

## 10. Migration and rollback checks

A new deployment must start from an empty PostgreSQL 16 + pgvector database:

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend \
  sh -c 'alembic upgrade head && alembic downgrade base && alembic upgrade head'
```

Revision `0003` uses Alembic batch mode, so the same migration path works on
SQLite and PostgreSQL. The CI workflow runs the empty-database upgrade and the
upgrade → downgrade base → upgrade round trip on every PR/push once activated.
For a code-only rollback, redeploy the previous immutable image tag. For a
schema/data rollback, stop traffic, take a fresh dump, use the reversible
Alembic downgrade only when the release notes permit it, or follow
`docs/DISASTER_RECOVERY.md` for restore.

## 11. Backups and recovery objectives

Run `scripts/backup.sh` daily at 02:15 UTC (or use an equivalent managed
PostgreSQL backup job), retain at least 14 dumps, and copy each dump to an
independent/off-site bucket. Redis is intentionally not restored: it is cache
and short-lived authentication throttle/blacklist state, so losing it logs
users out and resets limits rather than resurrecting stale credentials.

The documented single-region target is **RTO ≤ 60 minutes** and **RPO ≤ 24
hours** with daily logical dumps. Managed PostgreSQL PITR can improve the RPO
to minutes. The restore and release rollback runbooks are in
`docs/DISASTER_RECOVERY.md` and `docs/ROLLBACK_AND_VERSIONING.md`; perform a
quarterly restore drill against a real dump and record the measured RTO.

## 12. CI activation and evidence boundary

The complete workflow is versioned at `ci/github-ci.yml`, but this checkout's
GitHub App cannot create or update `.github/workflows/ci.yml`. A maintainer with
workflow-file permission must run:

```bash
cp .env.example .env                 # only for local compose validation
./scripts/enable_ci.sh
```

Then confirm a real GitHub Actions run and branch-protection checks in the
Actions UI. Until that happens, CI is **BLOCKED**, not active; local evidence
in `docs/agent-reports/infra-evidence/` does not substitute for a GitHub run.
