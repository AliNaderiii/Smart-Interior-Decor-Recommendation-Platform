#!/usr/bin/env python3
"""Probe: does a seed run create predictable demo / default-admin accounts?

Reproducible evidence for the Stage 03 top-priority requirement:

    "Production must never automatically create predictable demo users or
     default admin credentials."

The probe runs each seeding entrypoint in a **child process** with a throwaway
SQLite database and a fully production-shaped environment, then counts the rows
that landed in ``users``. It asserts nothing — it prints what actually happened,
so the same script produces meaningful output both before and after the fix.

Usage
-----
    cd backend
    .venv/bin/python ../docs/security/probes/probe_demo_seeding.py

Exit code is always 0; read the report.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3] / "backend"
DEMO_EMAILS = [
    "admin@smartdecor.dev",
    "designer@smartdecor.dev",
    "demo@smartdecor.dev",
]

# A production environment that satisfies every *existing* fail-fast check in
# Settings.validate_runtime(), so nothing else can mask the seeding behaviour.
PROD_ENV = {
    "APP_ENV": "production",
    "SECRET_KEY": "p" * 48,
    "REDIS_URL": "redis://127.0.0.1:6399/9",
    "COOKIE_SECURE": "true",
    "AI_PROVIDER": "mock",
    "EMBEDDING_BACKEND": "hash",
    "STORAGE_BACKEND": "local",
    "PAYMENT_PROVIDER": "mock",
}

DEV_ENV = dict(PROD_ENV, APP_ENV="development", COOKIE_SECURE="false")


def _count_users(db_path: Path) -> list[tuple[str, str]]:
    import sqlite3

    if not db_path.exists():
        return []
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("select email, role from users order by email").fetchall()
    except sqlite3.OperationalError:
        rows = []  # table never created
    finally:
        con.close()
    return rows


def run_case(name: str, argv: list[str], env_overrides: dict[str, str]) -> dict:
    workdir = Path(tempfile.mkdtemp(prefix="seedprobe-"))
    db_path = workdir / "probe.sqlite3"
    env = dict(os.environ)
    env.pop("DATABASE_URL", None)
    env.update(env_overrides)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["LOCAL_STORAGE_DIR"] = str(workdir / "storage")
    # Never let a stray repo-root .env leak into the probe.
    env["ENV_FILE"] = str(workdir / "nonexistent.env")

    proc = subprocess.run(
        [sys.executable, *argv],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    users = _count_users(db_path)
    demo_hits = [(e, r) for e, r in users if e in DEMO_EMAILS]
    result = {
        "case": name,
        "argv": " ".join(argv),
        "APP_ENV": env_overrides.get("APP_ENV"),
        "SEED_DEMO_ACCOUNTS": env_overrides.get("SEED_DEMO_ACCOUNTS", "<unset>"),
        "exit_code": proc.returncode,
        "users_created": len(users),
        "demo_accounts_created": demo_hits,
        "stdout_tail": proc.stdout.strip().splitlines()[-6:],
        "stderr_tail": proc.stderr.strip().splitlines()[-6:],
    }
    shutil.rmtree(workdir, ignore_errors=True)
    return result


CASES = [
    (
        "load_realistic_products.py in PRODUCTION (docker-compose boot command)",
        ["scripts/load_realistic_products.py", "--realistic", "--expand-to", "150",
         "--if-empty", "--from-json"],
        PROD_ENV,
    ),
    (
        "seed_products.py in PRODUCTION",
        ["scripts/seed_products.py", "--if-empty"],
        PROD_ENV,
    ),
    (
        "load_realistic_products.py in PRODUCTION with SEED_DEMO_ACCOUNTS=true "
        "(explicit opt-in must still be refused)",
        ["scripts/load_realistic_products.py", "--realistic", "--if-empty"],
        dict(PROD_ENV, SEED_DEMO_ACCOUNTS="true"),
    ),
    (
        "load_realistic_products.py in DEVELOPMENT, no opt-in",
        ["scripts/load_realistic_products.py", "--realistic", "--if-empty"],
        DEV_ENV,
    ),
    (
        "load_realistic_products.py in DEVELOPMENT with SEED_DEMO_ACCOUNTS=true",
        ["scripts/load_realistic_products.py", "--realistic", "--if-empty"],
        dict(DEV_ENV, SEED_DEMO_ACCOUNTS="true"),
    ),
    (
        "seed_products.py in DEVELOPMENT with SEED_DEMO_ACCOUNTS=true",
        ["scripts/seed_products.py", "--if-empty"],
        dict(DEV_ENV, SEED_DEMO_ACCOUNTS="true"),
    ),
]


def main() -> int:
    print("=" * 78)
    print("PROBE — predictable demo / default-admin account creation")
    print("=" * 78)
    results = []
    for name, argv, env in CASES:
        res = run_case(name, argv, env)
        results.append(res)
        print()
        print(f"--- {name}")
        print(f"    argv                 : {res['argv']}")
        print(f"    APP_ENV              : {res['APP_ENV']}")
        print(f"    SEED_DEMO_ACCOUNTS   : {res['SEED_DEMO_ACCOUNTS']}")
        print(f"    exit code            : {res['exit_code']}")
        print(f"    users rows created   : {res['users_created']}")
        print(f"    DEMO ACCOUNTS CREATED: {res['demo_accounts_created'] or 'NONE'}")
        for line in res["stderr_tail"]:
            print(f"    stderr| {line}")
        for line in res["stdout_tail"]:
            print(f"    stdout| {line}")

    prod_leaks = [
        r for r in results
        if r["APP_ENV"] == "production" and r["demo_accounts_created"]
    ]
    print()
    print("=" * 78)
    print(f"VERDICT: production runs that created demo accounts = {len(prod_leaks)}")
    print("         (requirement: 0)")
    print("=" * 78)
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
