#!/usr/bin/env bash
# ==============================================================================
# render_caddyfile.sh — derive Caddyfile.staging from the committed Caddyfile
# ==============================================================================
# The committed ./Caddyfile is the single source of truth for the security
# header block, including the CSP that backend/tests/test_csp_alignment.py
# pins byte-for-byte against build_csp(). This script must therefore NEVER
# rewrite a header line — it changes exactly two things:
#
#   1. the site address   ":443"       -> "<STAGING_HOST>"
#   2. the TLS block      "tls internal { protocols tls1.3 tls1.3 }"
#                         -> "tls { protocols tls1.3 tls1.3 }"
#      (real Let's Encrypt certificate instead of Caddy's local CA, TLS 1.3 only)
#
# Usage:
#   STAGING_HOST=staging.example.com ./scripts/render_caddyfile.sh [out]
#
# Default output: ./Caddyfile.staging (gitignored — it embeds the hostname).
# Re-running is idempotent: the output is a pure function of the inputs.
# ==============================================================================
set -euo pipefail

SRC="${CADDYFILE_SRC:-Caddyfile}"
OUT="${1:-Caddyfile.staging}"
HOST="${STAGING_HOST:-}"

if [ -z "$HOST" ]; then
  echo "FATAL: STAGING_HOST is not set (e.g. STAGING_HOST=staging.example.com)" >&2
  exit 2
fi
if [ ! -f "$SRC" ]; then
  echo "FATAL: source Caddyfile not found at '$SRC' (run from the repo root)" >&2
  exit 2
fi
case "$HOST" in
  *[!a-zA-Z0-9.-]*|-*|.*|*.)
    echo "FATAL: '$HOST' is not a plain hostname (no scheme, port, or path)" >&2
    exit 2 ;;
esac

ACME_EMAIL="${ACME_EMAIL:-admin@${HOST#*.}}"
TAB=$(printf '\t')

awk -v host="$HOST" -v email="$ACME_EMAIL" '
  # site address
  /^:443 \{$/           { print host " {"; next }
  # real ACME certificate instead of Caddy internal CA; TLS 1.3 stays pinned
  /^\ttls internal \{$/  { print "\ttls {"; next }
  # ACME registration address
  /^\temail /            { print "\temail " email; next }
  { print }
' "$SRC" > "$OUT"

# ---- verification: the header block must be untouched ------------------------
header_lines() {
  # Every response-header directive in the site's `header { ... }` block:
  # two leading tabs, then either `Name "value"` or the `-Server` removal.
  grep -E "^${TAB}${TAB}([A-Za-z-]+ \"|-Server)" "$1" | sort
}
src_headers=$(header_lines "$SRC")
out_headers=$(header_lines "$OUT")
if [ "$src_headers" != "$out_headers" ]; then
  echo "FATAL: header block drifted during render — refusing to emit $OUT" >&2
  diff <(echo "$src_headers") <(echo "$out_headers") >&2 || true
  rm -f "$OUT"
  exit 1
fi
if ! grep -q "^${HOST} {" "$OUT"; then
  echo "FATAL: site address was not rewritten (source layout changed?)" >&2
  rm -f "$OUT"
  exit 1
fi
if grep -q 'tls internal' "$OUT"; then
  echo "FATAL: 'tls internal' survived — staging would serve an untrusted cert" >&2
  rm -f "$OUT"
  exit 1
fi

echo "rendered $OUT for host=$HOST (acme email=$ACME_EMAIL)"
echo "header block verified identical to $SRC (CSP single source of truth intact)"
