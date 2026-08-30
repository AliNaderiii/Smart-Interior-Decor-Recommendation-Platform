#!/usr/bin/env python3
"""Boot-time configuration gate for the public demo container.

The single-container sibling of ``scripts/assert_staging_env.py`` (asset-reuse
map N3). It reads the LIVE settings object rather than a ``.env`` file, because
in a Hugging Face Space the configuration arrives as environment variables and
Space secrets — there is no file to parse.

What it enforces, and why each one matters on a PUBLIC demo:

  API_DOCS_MODE=disabled ... D-4.1 condition, BINDING. The container runs
                             APP_ENV=development on purpose (mock AI + local
                             storage are refused under production by design),
                             so "not production" is not a safe test. Without
                             the explicit switch this public URL would publish
                             an interactive map of the whole API.
  SECRET_KEY non-default ... the deploy workflow injects a generated key as a
                             Space secret; the documented dev default on a
                             public host would make every JWT forgeable.
  REDIS_URL set ............ fakeredis is per-process, so the JWT blacklist,
                             brute-force lockout and rate limits would not be
                             shared and could be bypassed by hitting another
                             worker.
  AI_PROVIDER=mock ......... no credential may exist on a public demo box.
  PAYMENT_PROVIDER sandbox . no real money may move.
  demo accounts enabled .... this is the demo; but see the boot-time proof in
                             entrypoint.sh that production still refuses them.

Exit 0 = safe to serve. Exit 1 = refuse to boot.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from app.core.config import settings  # noqa: E402

GREEN, RED, YELLOW, RESET = "\033[0;32m", "\033[0;31m", "\033[0;33m", "\033[0m"

failures: list[str] = []
notes: list[str] = []


def check(ok: bool, name: str, detail: str) -> None:
    tag = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"[demo]     {tag}  {name}: {detail}")
    if not ok:
        failures.append(f"{name}: {detail}")


def note(name: str, detail: str) -> None:
    print(f"[demo]     {YELLOW}NOTE{RESET}  {name}: {detail}")
    notes.append(f"{name}: {detail}")


# --- the binding D-4.1 condition ---------------------------------------------
check(
    not settings.api_docs_enabled,
    "interactive docs",
    "/docs, /redoc and /openapi.json are OFF (API_DOCS_MODE="
    f"{settings.API_DOCS_MODE})"
    if not settings.api_docs_enabled
    else f"EXPOSED — API_DOCS_MODE={settings.API_DOCS_MODE} on a public demo; "
         "set API_DOCS_MODE=disabled (D-4.1 condition)",
)

# --- credentials --------------------------------------------------------------
default_secret = settings.SECRET_KEY == settings.DEFAULT_SECRET
check(
    not default_secret and len(settings.SECRET_KEY) >= 32,
    "SECRET_KEY",
    f"{len(settings.SECRET_KEY)} chars, non-default"
    if not default_secret and len(settings.SECRET_KEY) >= 32
    else "still the documented default or too short — the deploy workflow must "
         "inject a generated key as a Space secret",
)

# --- shared state -------------------------------------------------------------
check(
    bool(settings.REDIS_URL),
    "REDIS_URL",
    settings.REDIS_URL
    or "empty — fakeredis is per-process, so rate limits and brute-force "
       "lockouts would be bypassable",
)

# --- no third-party credentials on a public box -------------------------------
check(
    settings.AI_PROVIDER == "mock",
    "AI_PROVIDER",
    "mock — no API key on a public demo (D-4/R3)"
    if settings.AI_PROVIDER == "mock"
    else f"{settings.AI_PROVIDER} — a real provider implies a credential on a "
         "public demo box",
)
check(
    not settings.GEMINI_API_KEY and not settings.OPENAI_API_KEY,
    "AI credentials",
    "none present"
    if not settings.GEMINI_API_KEY and not settings.OPENAI_API_KEY
    else "an AI API key is set on the public demo container",
)
check(
    settings.PAYMENT_PROVIDER in {"zarinpal_sandbox", "mock"},
    "PAYMENT_PROVIDER",
    f"{settings.PAYMENT_PROVIDER} — no real money moves"
    if settings.PAYMENT_PROVIDER in {"zarinpal_sandbox", "mock"}
    else f"{settings.PAYMENT_PROVIDER} is a LIVE payment provider",
)
check(
    settings.EMAIL_PROVIDER == "mock" or not settings.RESEND_API_KEY,
    "EMAIL",
    f"{settings.EMAIL_PROVIDER}"
    if settings.EMAIL_PROVIDER == "mock" or not settings.RESEND_API_KEY
    else "a live email credential is set on the public demo container",
)

# --- the demo profile itself ---------------------------------------------------
check(
    settings.SEED_DEMO_ACCOUNTS,
    "SEED_DEMO_ACCOUNTS",
    "true — the three demo logins exist (client decision C-7); production "
    "refusal is re-proven at boot"
    if settings.SEED_DEMO_ACCOUNTS
    else "false — the demo needs its logins",
)
check(
    not settings.is_production,
    "APP_ENV",
    f"{settings.APP_ENV} (D-4.1: mock AI + local storage are refused under "
    "production by design; docs are closed by the explicit switch above)"
    if not settings.is_production
    else "production — this image's mock/local profile cannot boot production",
)

# --- documented deviations, stated rather than hidden --------------------------
if settings.STORAGE_BACKEND == "local":
    note("STORAGE_BACKEND", "local — ephemeral demo media (D-4a: wiped on restart)")
note("persistence", "the database is re-created and re-seeded on every restart (D-4a)")

print("[demo]     " + "-" * 56)
if failures:
    print(f"[demo]     {RED}CONFIGURATION GATE: FAIL{RESET} — {len(failures)} problem(s)")
    for f in failures:
        print(f"[demo]       - {f}")
    sys.exit(1)
print(f"[demo]     {GREEN}CONFIGURATION GATE: PASS{RESET} "
      f"({len(notes)} documented deviation(s))")
