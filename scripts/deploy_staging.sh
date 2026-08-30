#!/usr/bin/env bash
# ==============================================================================
# deploy_staging.sh — one-command, re-runnable staging deploy      [Stage 4, T-4.1]
# ==============================================================================
# Run as the deploy user, from the repository root, on the staging host:
#
#   ./scripts/deploy_staging.sh                 # full deploy
#   ./scripts/deploy_staging.sh --no-pull       # deploy the working tree as-is
#   ./scripts/deploy_staging.sh --dry-run       # print the plan, change nothing
#
# Pipeline (each step is idempotent; a re-run converges to the same end state):
#   0  preflight     — tools, repo root, .env present + chmod 600
#   1  env gate      — scripts/assert_staging_env.py (production-grade checks)
#   2  pull          — fast-forward the deploy branch (skippable)
#   3  caddy render  — Caddyfile.staging from the committed Caddyfile (host+TLS only)
#   4  build         — docker compose build (brand args from .env)
#   5  up            — start postgres, redis, backend, frontend, caddy, maintenance
#   6  migrate       — alembic upgrade head (runs in the backend entrypoint; asserted here)
#   7  seed          — 150-product catalog, --if-empty (idempotent) + demo accounts
#   8  health        — wait for /api/v1/health/ready, then the public HTTPS origin
#   9  invariant     — re-prove APP_ENV=production refuses demo accounts
#  10  smoke         — scripts/smoke_staging.sh against the public origin
#  11  fingerprint   — end-state fingerprint for the idempotency evidence (3 runs)
#
# Every run appends a fingerprint to deploy-state/fingerprint.log; three
# consecutive runs must produce three identical fingerprints (T-4.1 DoD).
# ==============================================================================
set -euo pipefail

# ---- options -----------------------------------------------------------------
DO_PULL=1
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --no-pull) DO_PULL=0 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
STATE_DIR="deploy-state"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.staging.yml)

step() { printf '\n\033[1;34m==> [%s] %s\033[0m\n' "$1" "$2"; }
ok()   { printf '    \033[0;32mOK\033[0m   %s\n' "$*"; }
info() { printf '    ---- %s\n' "$*"; }
die()  { printf '\n\033[0;31mFATAL: %s\033[0m\n' "$*" >&2; exit 1; }

# ---- 0. preflight ------------------------------------------------------------
step 0 "Preflight"
[ -f docker-compose.yml ] && [ -d backend ] \
  || die "run from the repository root"
missing=""
for tool in docker git python3 curl openssl; do
  command -v "$tool" >/dev/null 2>&1 || missing="${missing} ${tool}"
done
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  missing="${missing} docker-compose-plugin"
fi
if [ -n "$missing" ]; then
  # --dry-run only prints the plan, so it stays usable off-host (e.g. to review
  # the pipeline from a laptop); a real deploy must have every tool.
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '    \033[0;33mWARN\033[0m missing (dry run, ignored):%s\n' "$missing"
  else
    die "missing required tool(s):${missing} — run scripts/host_prep.sh"
  fi
fi
[ -f .env ] || die ".env not found — cp .env.staging.example .env && chmod 600 .env"

perms=$(stat -c '%a' .env)
if [ "$perms" != "600" ]; then
  chmod 600 .env
  ok ".env permissions tightened ${perms} -> 600"
else
  ok ".env permissions 600"
fi

# STAGING_HOST is the one value everything else is keyed to.
# Parsed by the SAME parser the gate uses, so a value with an inline comment or
# quotes can never be read two different ways (caught in T-4.1 self-verify).
STAGING_HOST="${STAGING_HOST:-$(python3 scripts/assert_staging_env.py .env --print STAGING_HOST)}"
[ -n "$STAGING_HOST" ] \
  || die "STAGING_HOST is not set in .env (e.g. STAGING_HOST=staging.example.com)"
ok "staging host: ${STAGING_HOST}"
if command -v docker >/dev/null 2>&1; then
  ok "docker: $(docker --version | cut -d, -f1)"
  docker compose version --short >/dev/null 2>&1 \
    && ok "compose: $(docker compose version --short)"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  step "-" "DRY RUN — planned actions"
  cat <<EOF
    1  python3 scripts/assert_staging_env.py .env --host ${STAGING_HOST}
    2  git pull --ff-only $( [ "$DO_PULL" -eq 1 ] || echo '(skipped: --no-pull)' )
    3  STAGING_HOST=${STAGING_HOST} ./scripts/render_caddyfile.sh Caddyfile.staging
    4  ${COMPOSE[*]} build
    5  ${COMPOSE[*]} up -d
    6  ${COMPOSE[*]} exec -T backend alembic current
    7  ${COMPOSE[*]} exec -T backend python scripts/load_realistic_products.py --realistic --expand-to 150 --if-empty
    8  curl https://${STAGING_HOST}/api/v1/health/ready
    9  ./scripts/prove_demo_refusal.sh
   10  ./scripts/smoke_staging.sh https://${STAGING_HOST}
EOF
  exit 0
fi

mkdir -p "$STATE_DIR"

# ---- 1. environment gate -----------------------------------------------------
step 1 "Environment gate (production-grade checks — see D-4.1)"
python3 scripts/assert_staging_env.py .env --host "$STAGING_HOST" \
  || die "environment gate failed — fix .env and re-run (nothing was deployed)"

# ---- 2. pull -----------------------------------------------------------------
step 2 "Source"
if [ "$DO_PULL" -eq 1 ]; then
  branch=$(git rev-parse --abbrev-ref HEAD)
  git fetch --quiet origin "$branch"
  git pull --ff-only --quiet origin "$branch"
  ok "branch ${branch} fast-forwarded"
else
  ok "--no-pull: deploying the working tree as-is"
fi
GIT_SHA=$(git rev-parse --short HEAD)
ok "commit ${GIT_SHA} ($(git log -1 --format=%s | cut -c1-60))"

# ---- 3. Caddyfile ------------------------------------------------------------
step 3 "Caddyfile for ${STAGING_HOST}"
STAGING_HOST="$STAGING_HOST" ./scripts/render_caddyfile.sh Caddyfile.staging \
  | sed 's/^/    /'

# ---- 4. build ----------------------------------------------------------------
step 4 "Build images"
set -o pipefail
"${COMPOSE[@]}" build 2>&1 | tail -20 | sed 's/^/    /'
ok "images built"

# ---- 5. up -------------------------------------------------------------------
step 5 "Start services"
"${COMPOSE[@]}" up -d --remove-orphans 2>&1 | sed 's/^/    /'
"${COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}' | sed 's/^/    /'

# ---- 6. migrations -----------------------------------------------------------
step 6 "Database migrations"
info "waiting for the backend container to finish 'alembic upgrade head'"
for i in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T backend alembic current 2>/dev/null | grep -q '(head)'; then
    break
  fi
  sleep 5
  [ "$i" -lt 60 ] || die "alembic did not reach head within 5 minutes"
done
"${COMPOSE[@]}" exec -T backend alembic current 2>&1 | sed 's/^/    /'
ok "schema at head"

# ---- 7. catalog + demo accounts ----------------------------------------------
step 7 "Catalog and demo accounts (idempotent)"
"${COMPOSE[@]}" exec -T backend \
  python scripts/load_realistic_products.py --realistic --expand-to 150 --if-empty \
  2>&1 | tail -12 | sed 's/^/    /'

PRODUCT_COUNT=$("${COMPOSE[@]}" exec -T postgres \
  psql -U "${POSTGRES_USER:-decor}" -d "${POSTGRES_DB:-decor}" \
  -tAc 'select count(*) from products' 2>/dev/null | tr -d '\r ')
USER_COUNT=$("${COMPOSE[@]}" exec -T postgres \
  psql -U "${POSTGRES_USER:-decor}" -d "${POSTGRES_DB:-decor}" \
  -tAc 'select count(*) from users' 2>/dev/null | tr -d '\r ')
ok "products=${PRODUCT_COUNT} users=${USER_COUNT}"
[ "${PRODUCT_COUNT:-0}" -ge 150 ] \
  || die "expected >=150 products, found ${PRODUCT_COUNT:-0}"

# ---- 8. health ---------------------------------------------------------------
step 8 "Health"
info "internal readiness"
"${COMPOSE[@]}" exec -T backend python -c \
  "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready',timeout=5); print(r.status, r.read().decode()[:200])" \
  | sed 's/^/    /'

info "public origin https://${STAGING_HOST} (Caddy needs a moment for ACME on first run)"
public_ok=0
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
    "https://${STAGING_HOST}/api/v1/health/ready" || echo 000)
  if [ "$code" = "200" ]; then public_ok=1; break; fi
  [ $((i % 5)) -eq 0 ] && info "attempt ${i}/30 -> HTTP ${code}, retrying"
  sleep 10
done
[ "$public_ok" -eq 1 ] \
  || die "public health check never returned 200 (last HTTP ${code:-000}) — check DNS, port 443, and 'docker compose logs caddy'"
curl -sSi --max-time 10 "https://${STAGING_HOST}/api/v1/health/ready" \
  | head -20 | sed 's/^/    /'
ok "public HTTPS origin serving"

# ---- 9. invariant regression -------------------------------------------------
step 9 "Invariant: APP_ENV=production still refuses demo accounts"
./scripts/prove_demo_refusal.sh "${STATE_DIR}/demo-refusal-$(date -u +%Y%m%d_%H%M%SZ).txt" \
  | sed 's/^/    /'
ok "invariant holds"

# ---- 10. smoke ---------------------------------------------------------------
step 10 "Smoke test"
./scripts/smoke_staging.sh "https://${STAGING_HOST}" | sed 's/^/    /'

# ---- 11. fingerprint ---------------------------------------------------------
step 11 "End-state fingerprint (idempotency evidence)"
FINGERPRINT=$(cat <<EOF
commit=${GIT_SHA}
alembic=$("${COMPOSE[@]}" exec -T backend alembic current 2>/dev/null | grep -o '[0-9a-f]\{8,\} (head)' | head -1)
products=${PRODUCT_COUNT}
users=${USER_COUNT}
services=$("${COMPOSE[@]}" ps --services --filter status=running | sort | tr '\n' ',')
images=$("${COMPOSE[@]}" images --quiet | sort | md5sum | cut -c1-12)
caddyfile=$(md5sum Caddyfile.staging | cut -c1-12)
EOF
)
# shellcheck disable=SC2001  # line-anchored indent of a multi-line value
echo "$FINGERPRINT" | sed 's/^/    /'
{
  echo "--- run at ${STARTED_AT} (finished $(date -u +%Y-%m-%dT%H:%M:%SZ)) ---"
  echo "$FINGERPRINT"
} >> "${STATE_DIR}/fingerprint.log"

runs=$(grep -c '^--- run at' "${STATE_DIR}/fingerprint.log")
uniq_fp=$(grep -v '^--- run at' "${STATE_DIR}/fingerprint.log" | sort -u | md5sum | cut -c1-12)
info "recorded run #${runs} in ${STATE_DIR}/fingerprint.log"
if [ "$runs" -ge 3 ]; then
  distinct=$(awk '/^--- run at/{if(b!="")print b; b=""; next}{b=b $0 ";"}END{if(b!="")print b}' \
    "${STATE_DIR}/fingerprint.log" | sed 's/commit=[^;]*;//' | sort -u | wc -l)
  if [ "$distinct" -eq 1 ]; then
    ok "IDEMPOTENCY PROVEN: ${runs} runs, 1 distinct end state (${uniq_fp})"
  else
    printf '    \033[0;33mWARN\033[0m %s\n' \
      "${runs} runs produced ${distinct} distinct end states — inspect ${STATE_DIR}/fingerprint.log"
  fi
fi

step "DONE" "Staging deploy complete"
cat <<EOF
    URL       : https://${STAGING_HOST}
    commit    : ${GIT_SHA}
    products  : ${PRODUCT_COUNT}
    evidence  : ${STATE_DIR}/fingerprint.log, ${STATE_DIR}/demo-refusal-*.txt

    Relay to the agent: this output (run with | tee ~/deploy-runN.log), plus
      openssl s_client -connect ${STAGING_HOST}:443 -tls1_3 </dev/null 2>&1 | head -30
      curl -sSI https://${STAGING_HOST}/
EOF
