#!/usr/bin/env python3
"""Staging .env gate — the production fail-safes that still apply to a demo box.

Why this file exists (decision D-4.1, Stage 4 / T-4.1)
-----------------------------------------------------
Staging runs ``APP_ENV=development`` because supervisor ruling R3 mandates
``AI_PROVIDER=mock`` + ``STORAGE_BACKEND=local``, and
``Settings.validate_runtime()`` correctly refuses to boot *production* with
either of those. We did **not** weaken ``validate_runtime`` to accommodate that
(global invariant §2.8, gate discipline). Instead this script re-asserts, at
deploy time, every production check that still matters for a PUBLIC host:

    strong non-default SECRET_KEY .......... else JWTs are forgeable
    real shared REDIS_URL .................. else rate limits/lockouts are per-worker
    https FRONTEND_ORIGIN .................. else CORS + cookies break
    COOKIE_SECURE=true ..................... else session cookies leak over http
    non-default POSTGRES_PASSWORD .......... else trivial DB takeover
    FERNET_KEY valid or empty-by-choice .... else at-rest ciphertext is unrecoverable
    PAYMENT_CALLBACK_URL on the staging host  else the payment round-trip 404s

and the two waivers are stated explicitly rather than hidden:

    AI_PROVIDER=mock ....... WAIVED by R3 (deferred account); Stage 5 must set a real provider
    STORAGE_BACKEND=local .. WAIVED by R3 (local media volume); Stage 5 must set s3

Exit codes: 0 = pass, 1 = at least one FAIL. Usage::

    python3 scripts/assert_staging_env.py .env --host staging.example.com
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_SECRET = "dev-only-secret-change-me"
DEFAULT_DB_PASSWORDS = {"decor", "postgres", "changeme", "password", ""}

GREEN, RED, YELLOW, RESET = "\033[0;32m", "\033[0;31m", "\033[0;33m", "\033[0m"


def parse_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        # Strip inline comments on unquoted values. An EMPTY value followed by
        # a comment (`SECRET_KEY=      # [FILL]`) is the common template shape
        # and must parse as "" — not as the comment text, which would sail
        # through a length check and let an unfilled template deploy.
        if value[:1] not in {'"', "'"}:
            if value.startswith("#"):
                value = ""
            else:
                value = re.split(r"\s+#", value, maxsplit=1)[0]
        env[key.strip()] = value.strip().strip("\"'")
    return env


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.waivers: list[str] = []

    def check(self, ok: bool, name: str, detail: str) -> None:
        if ok:
            print(f"  {GREEN}PASS{RESET}  {name}: {detail}")
        else:
            print(f"  {RED}FAIL{RESET}  {name}: {detail}")
            self.failures.append(f"{name}: {detail}")

    def waive(self, name: str, detail: str) -> None:
        print(f"  {YELLOW}WAIVED{RESET} {name}: {detail}")
        self.waivers.append(f"{name}: {detail}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("env_file", nargs="?", default=".env")
    ap.add_argument("--host", help="staging hostname, e.g. staging.example.com")
    ap.add_argument("--print", dest="print_key", metavar="KEY",
                    help="print one parsed value and exit (used by "
                         "deploy_staging.sh so shell and gate parse identically)")
    args = ap.parse_args()

    if args.print_key:
        path = Path(args.env_file)
        if not path.exists():
            return 1
        print(parse_env(path).get(args.print_key, ""))
        return 0

    path = Path(args.env_file)
    if not path.exists():
        print(f"{RED}FATAL{RESET}: {path} not found "
              f"(cp .env.staging.example .env && chmod 600 .env)")
        return 1

    env = parse_env(path)
    host = args.host or env.get("STAGING_HOST", "")
    r = Report()

    print(f"\nStaging environment gate — {path} "
          f"(host={host or 'UNSET'})\n" + "-" * 62)

    # --- identity / crypto ----------------------------------------------------
    secret = env.get("SECRET_KEY", "")
    r.check(secret != DEFAULT_SECRET and len(secret) >= 32,
            "SECRET_KEY",
            f"{len(secret)} chars, non-default"
            if secret != DEFAULT_SECRET and len(secret) >= 32
            else "must be >=32 chars and not the documented default "
                 "(openssl rand -hex 32)")

    fernet = env.get("FERNET_KEY", "")
    if fernet:
        try:
            from cryptography.fernet import Fernet  # type: ignore

            Fernet(fernet.encode())
            valid = True
        except ImportError:
            valid = bool(re.fullmatch(r"[A-Za-z0-9_\-]{43}=", fernet))
        except Exception:
            valid = False
        r.check(valid, "FERNET_KEY", "valid urlsafe-base64 32-byte key"
                if valid else "not a valid Fernet key")
    else:
        r.check(False, "FERNET_KEY",
                "empty — a random key per process makes at-rest ciphertext "
                "unrecoverable across restarts "
                "(python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\")")

    # --- session / origin -----------------------------------------------------
    origin = env.get("FRONTEND_ORIGIN", "")
    r.check(origin.startswith("https://"), "FRONTEND_ORIGIN",
            origin or "empty — must be the exact https origin of the staging host")
    if host and origin:
        r.check(origin.rstrip("/") == f"https://{host}", "FRONTEND_ORIGIN host",
                f"{origin} matches https://{host}"
                if origin.rstrip("/") == f"https://{host}"
                else f"{origin} does not match the deploy host https://{host} "
                     f"— CORS will reject the SPA")

    r.check(env.get("COOKIE_SECURE", "").lower() == "true", "COOKIE_SECURE",
            "true" if env.get("COOKIE_SECURE", "").lower() == "true"
            else "must be true on a public HTTPS host")

    # --- shared state ---------------------------------------------------------
    redis_url = env.get("REDIS_URL", "")
    r.check(redis_url.startswith("redis://"), "REDIS_URL",
            redis_url or "empty — fakeredis is per-worker, so the JWT blacklist, "
                         "brute-force lockout and rate limits are bypassable")

    # --- database -------------------------------------------------------------
    pg_pass = env.get("POSTGRES_PASSWORD", "")
    r.check(pg_pass.lower() not in DEFAULT_DB_PASSWORDS and len(pg_pass) >= 16,
            "POSTGRES_PASSWORD",
            f"{len(pg_pass)} chars, non-default"
            if pg_pass.lower() not in DEFAULT_DB_PASSWORDS and len(pg_pass) >= 16
            else "must be >=16 chars and not a well-known default "
                 "(openssl rand -base64 24)")

    # --- payment round-trip ---------------------------------------------------
    callback = env.get("PAYMENT_CALLBACK_URL", "")
    if host:
        r.check(callback.startswith(f"https://{host}"), "PAYMENT_CALLBACK_URL",
                callback if callback.startswith(f"https://{host}")
                else f"{callback or 'empty'} — must point at https://{host}/... "
                     f"or the gateway cannot return the user")
    else:
        r.check(callback.startswith("https://"), "PAYMENT_CALLBACK_URL",
                callback or "empty")

    # --- leftover template placeholders ------------------------------------
    placeholders = sorted(
        k for k, v in env.items()
        if v and ("CHANGEME" in v.upper() or v.strip() in {"[FILL]", "<fill>"})
    )
    r.check(not placeholders, "template placeholders",
            "none left"
            if not placeholders
            else f"unfilled: {', '.join(placeholders)}")

    # --- staging profile assertions ------------------------------------------
    r.check(env.get("APP_ENV", "") == "development", "APP_ENV",
            "development (D-4.1: mock AI + local storage are refused under "
            "production by design; the compose overlay pins the "
            "production-shaped settings explicitly)"
            if env.get("APP_ENV") == "development"
            else f"expected 'development' on staging, got "
                 f"{env.get('APP_ENV', 'unset')!r} — see docker-compose.staging.yml")

    r.check(env.get("SEED_DEMO_ACCOUNTS", "").lower() == "true",
            "SEED_DEMO_ACCOUNTS",
            "true (staging demo logins, client decision C-7)"
            if env.get("SEED_DEMO_ACCOUNTS", "").lower() == "true"
            else "staging needs demo accounts for the client demo")

    demo_pw = env.get("DEMO_ACCOUNT_PASSWORD", "")
    r.check(len(demo_pw) >= 12, "DEMO_ACCOUNT_PASSWORD",
            f"{len(demo_pw)} chars (randomized, delivered out-of-band)"
            if len(demo_pw) >= 12
            else "set a randomized password (>=12 chars) — the documented "
                 "dev defaults must never guard a public host "
                 "(openssl rand -base64 18)")

    # --- explicit R3 waivers --------------------------------------------------
    if env.get("AI_PROVIDER") == "mock":
        r.waive("AI_PROVIDER", "mock — supervisor ruling R3 (no key on a public "
                               "demo box). Stage 5 must set gemini/openai.")
    if env.get("STORAGE_BACKEND") == "local":
        r.waive("STORAGE_BACKEND", "local — supervisor ruling R3 (local media "
                                   "volume). Stage 5 must set s3 + S3_*.")

    print("-" * 62)
    if r.failures:
        print(f"{RED}RESULT: FAIL{RESET} — {len(r.failures)} problem(s):")
        for f in r.failures:
            print(f"  - {f}")
        return 1
    print(f"{GREEN}RESULT: PASS{RESET} — {len(r.waivers)} documented waiver(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
