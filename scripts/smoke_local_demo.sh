#!/usr/bin/env bash
# ==============================================================================
# smoke_local_demo.sh — origin smoke test for the demo CONTAINER   [Stage 4, D-4.5]
# ==============================================================================
# Sibling of scripts/smoke_staging.sh, for the runner-hosted equivalence run
# (Directive 4, Option 3). smoke_staging.sh is deliberately NOT modified: it is
# the Stage-5 artifact for a real public host and must stay intact.
#
#   ./scripts/smoke_local_demo.sh http://127.0.0.1:7860
#
# WHAT THIS COVERS vs smoke_staging.sh — stated plainly, nothing is quietly
# dropped:
#
#   checks 1-4 of smoke_staging.sh (DNS resolution, http->https redirect,
#   TLS 1.3 handshake, HSTS) are EDGE concerns that only exist on a real
#   public host with a certificate. There is no such edge here: the container
#   is reached over plain http on loopback. They are NOT tested and NOT
#   claimed — they move to Stage 5 with the public URL (deviation D-4c).
#
#   everything that is a property of the APPLICATION and the container's own
#   nginx is tested here, plus the docs-off lock and the demo accounts.
#
# Exit code: 0 only if every check passes.
# ==============================================================================
set -uo pipefail

BASE="${1:-}"
if [ -z "$BASE" ]; then
  echo "usage: $0 http://127.0.0.1:7860" >&2
  exit 2
fi
BASE="${BASE%/}"

PASS=0
FAIL=0
pass() { PASS=$((PASS + 1)); printf '  PASS  %s\n' "$*"; }
fail() {
  FAIL=$((FAIL + 1))
  printf '  FAIL  %s\n' "$*"
  # Under GitHub Actions also emit an annotation: raw step logs are not
  # retrievable from the agent sandbox, so stdout alone makes a smoke failure
  # undiagnosable remotely. Harmless when run locally.
  [ -n "${GITHUB_ACTIONS:-}" ] && printf '::error title=smoke::%s\n' "$*"
  return 0
}
note() { printf '  NOTE  %s\n' "$*"; }

echo "=== demo container smoke test ==="
echo "target : ${BASE}"
echo "date   : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
note "DNS / TLS / HSTS are not applicable to a loopback target — Stage 5 (D-4c)."
echo

req() { curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$@"; }

# ---- 1. health ---------------------------------------------------------------
code=$(req "${BASE}/api/v1/health")
if [ "$code" = "200" ]; then pass "/api/v1/health -> 200"; else fail "/api/v1/health -> ${code}"; fi

ready_body=$(curl -sS --max-time 20 "${BASE}/api/v1/health/ready" 2>/dev/null)
if printf '%s' "$ready_body" | grep -q '"database"' &&
   printf '%s' "$ready_body" | grep -qi '"redis"'; then
  if printf '%s' "$ready_body" | grep -qiE '"(status|database|redis)"\s*:\s*("ok"|"up"|true|"healthy")'; then
    pass "/api/v1/health/ready reports database + redis"
  else
    fail "/api/v1/health/ready is not healthy: ${ready_body:0:200}"
  fi
else
  fail "/api/v1/health/ready missing database/redis keys: ${ready_body:0:200}"
fi

# ---- 2. SPA ------------------------------------------------------------------
ctype=$(curl -sS -o /dev/null -w '%{content_type}' --max-time 20 "${BASE}/")
code=$(req "${BASE}/")
if [ "$code" = "200" ] && printf '%s' "$ctype" | grep -qi 'text/html'; then
  pass "SPA index -> 200 text/html"
else
  fail "SPA index -> ${code} (${ctype})"
fi

# SPA deep-link fallback: a client-side route must still return the shell.
code=$(req "${BASE}/quiz")
if [ "$code" = "200" ]; then pass "SPA fallback /quiz -> 200"; else fail "SPA fallback /quiz -> ${code}"; fi

# ---- 3. DOCS-OFF (D-4.1, binding) --------------------------------------------
# Sub-paths matter: /docs/oauth2-redirect is a real FastAPI route, so a naive
# exact-match location block would leave it open.
for path in /docs /redoc /openapi.json /docs/ /docs/oauth2-redirect /metrics; do
  code=$(req "${BASE}${path}")
  if [ "$code" = "404" ]; then
    pass "docs-off ${path} -> 404"
  else
    fail "docs-off ${path} -> ${code} (MUST be 404)"
  fi
done

# ---- 4. demo accounts --------------------------------------------------------
# Each account is attempted exactly ONCE: logging in twice per account would
# double-count the result and needlessly exercise the rate limiter.
JAR=""
login_one() {
  local email="$1" pw="$2" jar code
  jar=$(mktemp)
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 25 \
    -c "$jar" -H 'Content-Type: application/json' \
    -d "{\"email\":\"${email}\",\"password\":\"${pw}\"}" \
    "${BASE}/api/v1/auth/login")
  if [ "$code" = "200" ] && grep -q 'access_token' "$jar"; then
    pass "login ${email} -> 200 with session cookie"
    if [ -z "$JAR" ]; then JAR="$jar"; else rm -f "$jar"; fi
    return 0
  fi
  fail "login ${email} -> ${code}"
  rm -f "$jar"
  return 1
}

login_one "demo@smartdecor.dev"     "Demo1234!"  || true
login_one "designer@smartdecor.dev" "Design123!" || true
login_one "admin@smartdecor.dev"    "Admin123!"  || true

# ---- 5. catalog --------------------------------------------------------------
if [ -n "${JAR}" ] && [ -f "${JAR}" ]; then
  body=$(curl -sS --max-time 25 -b "${JAR}" "${BASE}/api/v1/products?limit=5" 2>/dev/null)
  if printf '%s' "$body" | grep -q '"id"'; then
    pass "authenticated /api/v1/products returns a non-empty catalog"
  else
    fail "authenticated /api/v1/products empty: ${body:0:200}"
  fi
  rm -f "${JAR}"
else
  fail "no authenticated session — catalog check skipped"
fi

# ---- 6. security headers from the container's nginx --------------------------
headers=$(curl -sSI --max-time 20 "${BASE}/" 2>/dev/null)
for h in X-Content-Type-Options X-Frame-Options Referrer-Policy; do
  if printf '%s' "$headers" | grep -qi "^${h}:"; then
    pass "header ${h} present"
  else
    fail "header ${h} missing"
  fi
done
if printf '%s' "$headers" | grep -qi '^Server:.*nginx/'; then
  note "Server header exposes a version — tighten before a public host (Stage 5)."
fi

echo
echo "=== ${PASS} passed, ${FAIL} failed ==="
[ "$FAIL" -eq 0 ]
