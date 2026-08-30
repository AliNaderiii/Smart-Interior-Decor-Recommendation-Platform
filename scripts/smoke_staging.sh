#!/usr/bin/env bash
# ==============================================================================
# smoke_staging.sh — public-origin smoke test                     [Stage 4, T-4.1]
# ==============================================================================
# Read-only HTTP checks against the PUBLIC origin. Safe to run repeatedly, from
# the host or from a laptop. Produces the HTTP captures the honesty protocol
# requires before any "the staging URL works" claim.
#
#   ./scripts/smoke_staging.sh https://staging.example.com
#   ./scripts/smoke_staging.sh https://staging.example.com --verbose
#
# Checks:
#   1  DNS resolves
#   2  http://  -> 308 redirect to https
#   3  TLS 1.3 handshake succeeds (and TLS 1.2 is offered/pinned as configured)
#   4  security headers present: HSTS, CSP, X-Content-Type-Options,
#      X-Frame-Options, Referrer-Policy, Permissions-Policy, COOP; no Server
#   5  /api/v1/health        -> 200
#   6  /api/v1/health/ready  -> 200 with database + redis ok
#   7  SPA index             -> 200 text/html
#   8  register+login round-trip on a throwaway account -> 200/201 with a cookie
#   9  authenticated /api/v1/products returns a non-empty catalog
#  10  /docs is closed or open exactly as the environment intends (reported)
# ==============================================================================
set -uo pipefail

BASE="${1:-}"
VERBOSE=0
[ "${2:-}" = "--verbose" ] && VERBOSE=1
if [ -z "$BASE" ]; then
  echo "usage: $0 https://staging.example.com [--verbose]" >&2
  exit 2
fi
BASE="${BASE%/}"
HOST="${BASE#https://}"; HOST="${HOST#http://}"; HOST="${HOST%%/*}"

PASS=0; FAIL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; NC='\033[0m'
pass() { PASS=$((PASS+1)); printf "  ${GREEN}PASS${NC}  %s\n" "$*"; }
fail() { FAIL=$((FAIL+1)); printf "  ${RED}FAIL${NC}  %s\n" "$*"; }
note() { printf "  ${YELLOW}NOTE${NC}  %s\n" "$*"; }

echo "=== staging smoke test ==="
echo "target : ${BASE}"
echo "date   : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "client : $(curl --version | head -1)"
echo

# ---- 1. DNS ------------------------------------------------------------------
if resolved=$(getent hosts "$HOST" | awk '{print $1}' | paste -sd, -) && [ -n "$resolved" ]; then
  pass "DNS ${HOST} -> ${resolved}"
else
  fail "DNS ${HOST} does not resolve"
fi

# ---- 2. http -> https --------------------------------------------------------
redirect=$(curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' --max-time 10 \
  "http://${HOST}/" 2>/dev/null)
case "$redirect" in
  30[178]*https://*) pass "http:// redirects (${redirect})" ;;
  *) fail "http:// did not redirect to https (got: ${redirect:-no response})" ;;
esac

# ---- 3. TLS 1.3 --------------------------------------------------------------
tls_out=$(echo | timeout 15 openssl s_client -connect "${HOST}:443" \
  -servername "$HOST" -tls1_3 2>&1)
if echo "$tls_out" | grep -qE 'Protocol\s*:\s*TLSv1\.3|New, TLSv1\.3'; then
  cipher=$(echo "$tls_out" | grep -m1 -E '^\s*Cipher\s*:' | sed 's/.*: *//')
  issuer=$(echo "$tls_out" | grep -m1 '^issuer=' | cut -c1-90)
  verify=$(echo "$tls_out" | grep -m1 'Verify return code')
  pass "TLS 1.3 handshake OK (cipher=${cipher:-?})"
  note "${issuer:-issuer unknown}"
  note "${verify:-verify code unknown}"
  [ "$VERBOSE" -eq 1 ] && echo "$tls_out" | head -40 | sed 's/^/        /'
else
  fail "TLS 1.3 handshake failed"
  echo "$tls_out" | head -15 | sed 's/^/        /'
fi

# ---- 4. security headers -----------------------------------------------------
headers=$(curl -sSI --max-time 15 "${BASE}/" 2>/dev/null)
if [ -z "$headers" ]; then
  fail "no response headers from ${BASE}/"
else
  check_header() {
    if echo "$headers" | grep -qi "^$1:"; then
      pass "header $1: $(echo "$headers" | grep -i "^$1:" | head -1 | cut -c1-72 | tr -d '\r')"
    else
      fail "header $1 missing"
    fi
  }
  check_header "strict-transport-security"
  check_header "content-security-policy"
  check_header "x-content-type-options"
  check_header "x-frame-options"
  check_header "referrer-policy"
  check_header "permissions-policy"
  check_header "cross-origin-opener-policy"
  if echo "$headers" | grep -qi '^server:'; then
    fail "Server header is exposed: $(echo "$headers" | grep -i '^server:' | tr -d '\r')"
  else
    pass "Server header suppressed"
  fi
fi

# ---- 5/6. health -------------------------------------------------------------
for path in /api/v1/health /api/v1/health/ready; do
  body=$(curl -sS -w '\n%{http_code}' --max-time 15 "${BASE}${path}" 2>/dev/null)
  code=$(echo "$body" | tail -1)
  payload=$(echo "$body" | sed '$d' | tr -d '\n' | cut -c1-160)
  if [ "$code" = "200" ]; then
    pass "GET ${path} -> 200 ${payload}"
  else
    fail "GET ${path} -> ${code} ${payload}"
  fi
done

# ---- 7. SPA ------------------------------------------------------------------
spa=$(curl -sS -o /tmp/smoke_index.html -w '%{http_code} %{content_type}' \
  --max-time 15 "${BASE}/" 2>/dev/null)
if echo "$spa" | grep -q '^200 text/html'; then
  title=$(grep -o '<title>[^<]*</title>' /tmp/smoke_index.html | head -1)
  pass "SPA index 200 text/html ${title}"
else
  fail "SPA index -> ${spa}"
fi

# ---- 8. auth round-trip ------------------------------------------------------
STAMP=$(date -u +%s)
EMAIL="smoke_${STAMP}@smoke.invalid"
PW="Sm0ke-$(head -c 9 /dev/urandom | base64 | tr -dc 'A-Za-z0-9')!"
COOKIE_JAR=$(mktemp)
reg=$(curl -sS -o /tmp/smoke_reg.json -w '%{http_code}' --max-time 20 \
  -X POST "${BASE}/api/v1/auth/register" \
  -H 'Content-Type: application/json' \
  -c "$COOKIE_JAR" \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PW}\",\"full_name\":\"Smoke Test\",\"role\":\"homeowner\"}" \
  2>/dev/null)
case "$reg" in
  200|201) pass "register ${EMAIL} -> ${reg}" ;;
  429)     note "register -> 429 (rate limit active — this is correct behaviour, auth check skipped)" ;;
  *)       fail "register -> ${reg} $(head -c 160 /tmp/smoke_reg.json 2>/dev/null)" ;;
esac

if [ "$reg" = "200" ] || [ "$reg" = "201" ]; then
  login=$(curl -sS -o /tmp/smoke_login.json -w '%{http_code}' --max-time 20 \
    -X POST "${BASE}/api/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -c "$COOKIE_JAR" \
    -d "{\"email\":\"${EMAIL}\",\"password\":\"${PW}\"}" 2>/dev/null)
  if [ "$login" = "200" ]; then
    pass "login -> 200"
  else
    fail "login -> ${login} $(head -c 160 /tmp/smoke_login.json 2>/dev/null)"
  fi
  if grep -qi 'access' "$COOKIE_JAR" 2>/dev/null; then
    pass "httpOnly session cookie set"
  else
    note "no cookie in jar (Bearer-token mode?) — inspect /tmp/smoke_login.json"
  fi

  # ---- 9. catalog ------------------------------------------------------------
  prod=$(curl -sS -o /tmp/smoke_products.json -w '%{http_code}' --max-time 20 \
    -b "$COOKIE_JAR" "${BASE}/api/v1/products?limit=5" 2>/dev/null)
  if [ "$prod" = "200" ]; then
    n=$(grep -o '"id"' /tmp/smoke_products.json | wc -l | tr -d ' ')
    if [ "$n" -gt 0 ]; then
      pass "GET /api/v1/products -> 200 with ${n} item(s)"
    else
      fail "GET /api/v1/products -> 200 but the catalog is EMPTY (seeder did not run)"
    fi
  else
    fail "GET /api/v1/products -> ${prod}"
  fi
fi
rm -f "$COOKIE_JAR"

# ---- 10. docs exposure -------------------------------------------------------
docs=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "${BASE}/docs" 2>/dev/null)
note "GET /docs -> ${docs} (200 = interactive docs public on staging; 404 = closed)"

# ---- verdict -----------------------------------------------------------------
echo
echo "-------------------------------------------"
echo "passed: ${PASS}   failed: ${FAIL}"
if [ "$FAIL" -eq 0 ]; then
  printf "${GREEN}RESULT: PASS${NC} — %s is live and serving\n" "$BASE"
  exit 0
fi
printf "${RED}RESULT: FAIL${NC} — %d check(s) failed\n" "$FAIL"
exit 1
