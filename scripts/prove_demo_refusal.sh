#!/usr/bin/env bash
# ==============================================================================
# prove_demo_refusal.sh — re-prove global invariant §2.3 on the staging host
# ==============================================================================
# Staging is the ONLY environment where demo accounts exist. That is only safe
# because production refuses them unconditionally. This script re-proves the
# refusal on the very host that runs the demo, using the deployed image, and
# writes a verbatim transcript for the evidence pack.
#
#   ./scripts/prove_demo_refusal.sh [output_file]
#
# Three independent proofs, all inside the running backend image:
#   1. Settings.validate_runtime() with APP_ENV=production + SEED_DEMO_ACCOUNTS=true
#      -> RuntimeError (the process would not boot at all)
#   2. demo_seed.demo_seeding_allowed() under APP_ENV=production -> False,
#      and with strict=True -> DemoSeedRefused
#   3. demo_seed.enable_for_this_process() under production -> DemoSeedRefused
#      (a deploy script cannot mistake a no-op for success)
#
# Exit non-zero if any proof does not behave as documented.
# ==============================================================================
set -euo pipefail

OUT="${1:-/dev/stdout}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.staging.yml)

{
  echo "=== demo-account production refusal proof ==="
  echo "date : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host : $(hostname)"
  echo "image: $("${COMPOSE[@]}" images backend --quiet 2>/dev/null | head -1)"
  echo
} > "$OUT"

"${COMPOSE[@]}" run --rm --no-deps \
  -e APP_ENV=production \
  -e SEED_DEMO_ACCOUNTS=true \
  -e SECRET_KEY=0000000000000000000000000000000000000000000000000000000000000000 \
  -e REDIS_URL=redis://redis:6379/0 \
  -e FRONTEND_ORIGIN=https://example.invalid \
  -e COOKIE_SECURE=true \
  backend python - <<'PY' >> "$OUT" 2>&1
import sys

failures = []

# ---- proof 1: the process refuses to boot ----------------------------------
from app.core.config import Settings
try:
    Settings().validate_runtime()
    failures.append("PROOF 1 FAILED: validate_runtime() accepted production + SEED_DEMO_ACCOUNTS=true")
    print("PROOF 1: FAILED — no exception raised")
except RuntimeError as exc:
    print("PROOF 1: validate_runtime() raised RuntimeError as designed")
    print("---- verbatim ----")
    print(exc)
    print("------------------")
    if "SEED_DEMO_ACCOUNTS" not in str(exc):
        failures.append("PROOF 1 FAILED: exception does not mention SEED_DEMO_ACCOUNTS")

# ---- proof 2: the seeding gate itself ---------------------------------------
from app.core import demo_seed
print()
allowed = demo_seed.demo_seeding_allowed()
print(f"PROOF 2a: demo_seeding_allowed() -> {allowed} (expected False)")
if allowed:
    failures.append("PROOF 2a FAILED: seeding allowed under production")

try:
    demo_seed.demo_seeding_allowed(strict=True)
    print("PROOF 2b: FAILED — strict=True did not raise")
    failures.append("PROOF 2b FAILED: strict mode did not raise DemoSeedRefused")
except demo_seed.DemoSeedRefused as exc:
    print(f"PROOF 2b: DemoSeedRefused raised as designed: {exc}")

# ---- proof 3: the CLI opt-in ------------------------------------------------
print()
try:
    demo_seed.enable_for_this_process(reason="staging refusal regression")
    print("PROOF 3: FAILED — enable_for_this_process() succeeded under production")
    failures.append("PROOF 3 FAILED: CLI opt-in was not refused")
except demo_seed.DemoSeedRefused as exc:
    print(f"PROOF 3: DemoSeedRefused raised as designed: {exc}")

print()
if failures:
    print("RESULT: FAIL")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("RESULT: PASS — demo accounts are not creatable under APP_ENV=production")
PY

status=$?
tail -3 "$OUT" 2>/dev/null || true
exit $status
