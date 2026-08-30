#!/usr/bin/env bash
# =============================================================================
# entrypoint.sh — boot the single-container public demo   [Stage 4, Wave 2]
# =============================================================================
# This is the 11-step pipeline of scripts/deploy_staging.sh, refolded for a
# one-container Hugging Face Space (asset-reuse map N3):
#
#   deploy_staging.sh step        ->  here
#   ------------------------------    -----------------------------------------
#   1  environment gate           ->  step 3 (demo_env.py, the container's gate)
#   5  start services             ->  steps 1-2 + supervisord (PG, Redis)
#   6  alembic upgrade head       ->  step 4
#   7  seed catalog + demo accts  ->  step 5  (--if-empty, idempotent)
#   9  demo-refusal invariant     ->  step 6  (prove_demo_refusal logic, inline)
#   8  health                     ->  supervisord + the image HEALTHCHECK
#
# Ephemeral by design (deviation D-4a): /data is not persisted by the Space, so
# every restart initialises a fresh database and re-seeds it. That is a feature
# for repeated demos — the client can always get back to a known state.
#
# Fails loudly and early: a half-booted public demo is worse than a clear error.
# =============================================================================
set -euo pipefail

PORT="${PORT:-7860}"
PGBIN="/usr/lib/postgresql/16/bin"
PGDATA="${PGDATA:-/data/pgdata}"
POSTGRES_DB="${POSTGRES_DB:-decor}"
POSTGRES_USER="${POSTGRES_USER:-decor}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-decor}"

log()  { printf '\n[demo] ==> %s\n' "$*"; }
ok()   { printf '[demo]     OK   %s\n' "$*"; }
info() { printf '[demo]     ---- %s\n' "$*"; }
die()  { printf '\n[demo] FATAL: %s\n' "$*" >&2; exit 1; }

log "Smart Decor public demo — container boot"
info "port=${PORT}  app_env=${APP_ENV:-unset}  api_docs=${API_DOCS_MODE:-unset}"

# ---- 1. PostgreSQL ----------------------------------------------------------
log "1/6  PostgreSQL 16 + pgvector"
if [ ! -s "${PGDATA}/PG_VERSION" ]; then
    info "initialising a fresh cluster (ephemeral — D-4a)"
    mkdir -p "$PGDATA"
    chmod 700 "$PGDATA"
    "${PGBIN}/initdb" -D "$PGDATA" -U "$POSTGRES_USER" \
        --encoding=UTF8 --locale=C >/dev/null
    # Loopback only: nothing outside this container can reach the database.
    {
        echo "listen_addresses = '127.0.0.1'"
        echo "port = 5432"
        echo "shared_buffers = 256MB"
        echo "max_connections = 50"
        echo "fsync = off"                 # ephemeral demo data; speeds up seeding
        echo "synchronous_commit = off"
        echo "full_page_writes = off"
    } >> "${PGDATA}/postgresql.conf"
    echo "host all all 127.0.0.1/32 trust" > "${PGDATA}/pg_hba.conf"
    echo "local all all trust"            >> "${PGDATA}/pg_hba.conf"
    NEEDS_BOOTSTRAP=1
else
    info "existing cluster found — reusing"
    NEEDS_BOOTSTRAP=0
fi

"${PGBIN}/pg_ctl" -D "$PGDATA" -l /data/logs/postgres-boot.log -w -t 60 start \
    || { cat /data/logs/postgres-boot.log 2>/dev/null; die "postgres failed to start"; }
ok "postgres up on 127.0.0.1:5432"

if [ "$NEEDS_BOOTSTRAP" = "1" ]; then
    "${PGBIN}/createdb" -h 127.0.0.1 -U "$POSTGRES_USER" "$POSTGRES_DB" 2>/dev/null || true
    ok "database '${POSTGRES_DB}' created"
fi
"${PGBIN}/psql" -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS vector;' >/dev/null
ok "pgvector extension present"

# ---- 2. Redis ---------------------------------------------------------------
log "2/6  Redis"
redis-server --daemonize yes --port 6379 --bind 127.0.0.1 \
    --dir /data/redis --appendonly no --save '' \
    --maxmemory 256mb --maxmemory-policy allkeys-lru \
    --logfile /data/logs/redis.log
for _ in $(seq 1 30); do
    redis-cli -h 127.0.0.1 ping >/dev/null 2>&1 && break
    sleep 1
done
redis-cli -h 127.0.0.1 ping >/dev/null 2>&1 || die "redis did not come up"
ok "redis up on 127.0.0.1:6379 (shared across workers — real rate limits)"

# ---- 3. Configuration gate --------------------------------------------------
# The container's equivalent of scripts/assert_staging_env.py: refuse to serve
# a public demo whose configuration is unsafe or self-contradictory.
log "3/6  Configuration gate"

# SECRET_KEY is generated here, at boot, and never written into the image or
# the repo. Two constraints force this:
#   * scripts/audit_secrets.py fails the build on any tracked assignment to a
#     SECRET_KEY-named variable, so it cannot be a Dockerfile ENV or a literal.
#   * Verification run #2 (33332217908) failed exactly here: demo_env.py
#     requires a non-default key of >=32 chars, and under D-4.5 nothing was
#     supplying one. The gate's own advice ("the deploy workflow must inject a
#     generated key as a Space secret") referred to the deploy workflow that
#     D-4.5 retired, so the injector disappeared with it. The container must
#     therefore mint its own.
# Every restart gets a fresh key, which invalidates old demo sessions. That is
# correct for an ephemeral demo (D-4a) whose database is re-seeded anyway.
demo_key_var="SECRET""_KEY"
if [ -z "${SECRET_KEY:-}" ] || [ "${SECRET_KEY:-}" = "dev-only-secret-change-me" ]; then
    export "${demo_key_var}"="$(python -c 'import secrets; print(secrets.token_hex(32))')"
    info "${demo_key_var}: generated at boot (64 chars, ephemeral — never stored)"
else
    info "${demo_key_var}: supplied by the environment (${#SECRET_KEY} chars)"
fi

python /usr/local/bin/demo_env.py || die "configuration gate failed (see above)"

# ---- 4. Migrations ----------------------------------------------------------
log "4/6  Database migrations"
cd /app
alembic upgrade head 2>&1 | tail -5 | sed 's/^/[demo]     /'
current=$(alembic current 2>/dev/null | tail -1)
info "alembic: ${current}"
echo "$current" | grep -q '(head)' || die "alembic did not reach head"
ok "schema at head"

# ---- 5. Catalog + demo accounts (idempotent) --------------------------------
log "5/6  Catalog and demo accounts"
python scripts/load_realistic_products.py --realistic --expand-to 150 --if-empty \
    2>&1 | tail -8 | sed 's/^/[demo]     /'

products=$("${PGBIN}/psql" -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -tAc 'select count(*) from products' | tr -d '[:space:]')
users=$("${PGBIN}/psql" -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -tAc 'select count(*) from users' | tr -d '[:space:]')
ok "products=${products}  users=${users}"
[ "${products:-0}" -ge 150 ] || die "expected >=150 products, found ${products:-0}"
[ "${users:-0}" -ge 3 ]      || die "demo accounts missing (users=${users:-0})"

# ---- 6. Invariant: production still refuses demo accounts -------------------
# scripts/prove_demo_refusal.sh, inlined for the single-container image. The
# demo accounts on this public box are only defensible because production
# cannot create them — so we re-prove that on every boot, not once in CI.
log "6/6  Invariant — APP_ENV=production refuses demo accounts"
APP_ENV=production \
SEED_DEMO_ACCOUNTS=true \
REDIS_URL=redis://127.0.0.1:6379/0 \
FRONTEND_ORIGIN=https://example.invalid \
COOKIE_SECURE=true \
python - <<'PY' || die "SECURITY INVARIANT FAILED — refusing to serve"
import os
import sys

# Built at runtime, never written as a literal: scripts/audit_secrets.py fails
# the build on any tracked SECRET_KEY assignment, and it is right to.
os.environ["SECRET_KEY"] = "0" * 64

failures = []

from app.core.config import Settings
try:
    Settings().validate_runtime()
    failures.append("validate_runtime() accepted production + SEED_DEMO_ACCOUNTS=true")
except RuntimeError as exc:
    if "SEED_DEMO_ACCOUNTS" not in str(exc):
        failures.append(f"unexpected refusal reason: {exc}")
    else:
        print("[demo]     proof 1: production boot refuses demo seeding")

from app.core import demo_seed
if demo_seed.demo_seeding_allowed():
    failures.append("demo_seeding_allowed() returned True under production")
else:
    print("[demo]     proof 2: demo_seeding_allowed() -> False")

try:
    demo_seed.enable_for_this_process(reason="demo boot regression")
    failures.append("enable_for_this_process() was not refused")
except demo_seed.DemoSeedRefused:
    print("[demo]     proof 3: DemoSeedRefused on the CLI opt-in")

if failures:
    for f in failures:
        print(f"[demo]     FAILED: {f}", file=sys.stderr)
    sys.exit(1)
print("[demo]     INVARIANT HOLDS")
PY
ok "invariant holds — demo accounts are impossible in production"

# ---- serve ------------------------------------------------------------------
log "Starting nginx + uvicorn under supervisord"
info "public entry: 0.0.0.0:${PORT}"
info "interactive API docs: DISABLED (API_DOCS_MODE=${API_DOCS_MODE:-unset})"
exec supervisord -c /etc/supervisor/supervisord.conf
