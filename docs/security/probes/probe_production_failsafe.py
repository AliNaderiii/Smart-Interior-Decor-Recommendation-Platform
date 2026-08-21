#!/usr/bin/env python3
"""Probe: does the application actually fail *safe* in production?

Stage 03 work items 1, 7 and 9. Every check here needs `APP_ENV=production`,
which the pytest suite cannot set globally (it would disable the whole
fixture set), so they run as child processes with a production-shaped
environment and their real output is captured.

The probe asserts nothing. It prints what the application did next to what a
fail-safe application should do, and the summary counts the checks whose
observed behaviour is unsafe.

Usage
-----
    cd backend
    .venv/bin/python ../docs/security/probes/probe_production_failsafe.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3] / "backend"
WORK = Path(tempfile.mkdtemp(prefix="prodfailsafe-"))

#: A production configuration that is correct in every respect.
GOOD_PROD = {
    "APP_ENV": "production",
    "SECRET_KEY": "p" * 48,
    "REDIS_URL": "redis://127.0.0.1:6399/12",
    "COOKIE_SECURE": "true",
    "COOKIE_SAMESITE": "strict",
    "FRONTEND_ORIGIN": "https://app.smartdecor.example",
    "FERNET_KEY": "2xLmTPRPYxxLW8mM3jXfKcXo5G3iVYkYfQ2vYbFsC8Y=",
    "STORAGE_BACKEND": "s3",
    "AI_PROVIDER": "mock",
    "EMBEDDING_BACKEND": "hash",
    "PAYMENT_PROVIDER": "mock",
    "SEED_DEMO_ACCOUNTS": "false",
}

results: list[tuple[str, str, str, str, bool]] = []


def run(script: str, env_overrides: dict[str, str],
        db_name: str = "prod.sqlite3") -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for key in ("SEED_DEMO_ACCOUNTS", "APP_ENV", "REDIS_URL", "COOKIE_SECURE",
                "FRONTEND_ORIGIN", "STORAGE_BACKEND", "FERNET_KEY", "SECRET_KEY"):
        env.pop(key, None)
    env.update(GOOD_PROD)
    env["DATABASE_URL"] = f"sqlite:///{WORK / db_name}"
    env["LOCAL_STORAGE_DIR"] = str(WORK / "media")
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=300,
    )


def check(check_id: str, title: str, expected: str, observed: str,
          secure: bool) -> None:
    results.append((check_id, title, expected, observed, secure))
    print(f"[{'SECURE  ' if secure else 'INSECURE'}] {check_id} {title}")
    print(f"           expected: {expected}")
    print(f"           observed: {observed}")


print("=" * 78)
print("PRODUCTION FAIL-SAFE PROBE")
print("=" * 78)
print(f"workdir: {WORK}")
print()

# ---------------------------------------------------------------- F-01 boot
proc = run(
    """
    from app.core.config import Settings
    import os
    cfg = Settings()
    try:
        cfg.validate_runtime()
        print("BOOTED")
    except RuntimeError as exc:
        print("REFUSED")
        print(exc)
    """,
    {"SECRET_KEY": "short", "REDIS_URL": "", "COOKIE_SECURE": "false",
     "STORAGE_BACKEND": "local", "FRONTEND_ORIGIN": "http://localhost:5173",
     "FERNET_KEY": "", "SEED_DEMO_ACCOUNTS": "true"},
)
refused = "REFUSED" in proc.stdout
problems = [line.strip(" -") for line in proc.stdout.splitlines()
            if line.strip().startswith("-")]
check("F-01", "An insecure production configuration must refuse to boot",
      "RuntimeError naming every problem",
      f"refused={refused} problems={len(problems)}: {problems}", refused)

# ---------------------------------------------------------------- F-02 good
proc = run("""
    from app.core.config import Settings
    Settings().validate_runtime()
    print("BOOTED")
""", {})
check("F-02", "A correct production configuration must boot",
      "no exception",
      f"stdout={proc.stdout.strip()!r} rc={proc.returncode}",
      proc.returncode == 0 and "BOOTED" in proc.stdout)

# ------------------------------------------------------- F-03 seeding refusal
proc = run("""
    from app.core.demo_seed import demo_seeding_allowed, enable_for_this_process
    print("allowed:", demo_seeding_allowed())
    try:
        enable_for_this_process()
        print("CLI OPT-IN ACCEPTED")
    except Exception as exc:
        print("CLI OPT-IN REFUSED:", exc)
""", {"SEED_DEMO_ACCOUNTS": "true"})
ok = "allowed: False" in proc.stdout and "CLI OPT-IN REFUSED" in proc.stdout
check("F-03", "Demo seeding must be refused in production, opt-in or not",
      "allowed: False and the CLI flag refused",
      " | ".join(proc.stdout.split()), ok)

# ------------------------------------------------------- F-04 boot DB guard
proc = run("""
    from app.db.session import SessionLocal, engine
    from app.models import Base
    from app.models.user import User
    from app.core.security import hash_password
    from app.core.demo_seed import assert_no_demo_accounts_in_production

    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add(User(email="admin@smartdecor.dev",
                hashed_password=hash_password("Admin123!"),
                full_name="Restored from a staging dump", role="admin"))
    db.commit()
    try:
        assert_no_demo_accounts_in_production(db)
        print("SERVED ANYWAY")
    except RuntimeError as exc:
        print("REFUSED TO SERVE:", exc)
""", {}, db_name="restored-dump.sqlite3")
ok = "REFUSED TO SERVE" in proc.stdout
check("F-04", "A production database containing demo rows must stop startup",
      "RuntimeError at boot",
      proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-200:],
      ok)

# --------------------------------------------------------- F-05 redis lock
proc = run("""
    from app.core.redis_client import get_redis, RedisUnavailable
    try:
        get_redis()
        print("FELL BACK TO FAKEREDIS")
    except RedisUnavailable as exc:
        print("REFUSED:", exc)
""", {"REDIS_URL": ""})
ok = "REFUSED" in proc.stdout
check("F-05", "Production must refuse the per-process fakeredis fallback",
      "RedisUnavailable",
      proc.stdout.strip()[:200] or proc.stderr[-200:], ok)

# ------------------------------------------------------ F-06 fail closed 503
proc = run("""
    from fastapi.testclient import TestClient
    from app.core import brute_force, rate_limit
    from app.db.session import engine
    from app.models import Base

    Base.metadata.create_all(engine)

    class Broken:
        def __getattr__(self, name):
            def boom(*a, **k):
                raise ConnectionError("redis is down")
            return boom

    rate_limit.get_redis = lambda: Broken()
    brute_force.get_redis = lambda: Broken()

    import app.main as main
    # The lifespan boot guard needs a database; the schema above is empty, so
    # there are no demo rows and it passes.
    with TestClient(main.app) as client:
        resp = client.post("/api/v1/auth/login",
                           json={"email": "someone@example.com",
                                 "password": "Whatever123!"})
        print("status:", resp.status_code)
        print("retry_after:", resp.headers.get("Retry-After"))
        print("csp:", bool(resp.headers.get("Content-Security-Policy")))
""", {}, db_name="failclosed.sqlite3")
status = next((line.split(": ")[1] for line in proc.stdout.splitlines()
               if line.startswith("status:")), "?")
retry = next((line.split(": ")[1] for line in proc.stdout.splitlines()
              if line.startswith("retry_after:")), "?")
ok = status == "503" and retry not in ("None", "?")
check("F-06", "With Redis down, production must fail CLOSED on login",
      "503 + Retry-After (never an unthrottled 401/200)",
      f"status={status} retry_after={retry} " +
      (proc.stderr.strip().splitlines()[-1][:160] if not ok and proc.stderr else ""),
      ok)

# ------------------------------------------------------- F-07 attack surface
proc = run("""
    import json
    import app.main as main
    paths = sorted({getattr(r, "path", "") for r in main.app.routes})
    print(json.dumps({
        "docs_url": main.app.docs_url,
        "openapi_url": main.app.openapi_url,
        "redoc_url": main.app.redoc_url,
        "cors_origins": main.build_cors_origins(),
        "media_mounted": "/media" in paths,
    }))
""", {}, db_name="surface.sqlite3")
try:
    info = json.loads(proc.stdout.strip().splitlines()[-1])
except Exception:
    info = {}
ok = (info.get("docs_url") is None and info.get("openapi_url") is None
      and info.get("redoc_url") is None
      and info.get("cors_origins") == ["https://app.smartdecor.example"]
      and info.get("media_mounted") is False)
check("F-07", "Production must not expose docs, loopback CORS or local media",
      "docs/openapi/redoc disabled, exactly one CORS origin, no /media mount",
      json.dumps(info) or proc.stderr[-200:], ok)

# ---------------------------------------------------------- F-08 HSTS + CSP
proc = run("""
    from fastapi.testclient import TestClient
    from app.db.session import engine
    from app.models import Base
    Base.metadata.create_all(engine)
    import app.main as main
    with TestClient(main.app) as client:
        r = client.get("/api/v1/health")
        print("hsts:", r.headers.get("Strict-Transport-Security"))
        print("csp:", r.headers.get("Content-Security-Policy"))
""", {}, db_name="headers.sqlite3")
hsts = next((line.split(": ", 1)[1] for line in proc.stdout.splitlines()
             if line.startswith("hsts:")), "None")
csp = next((line.split(": ", 1)[1] for line in proc.stdout.splitlines()
            if line.startswith("csp:")), "None")
ok = "max-age=" in hsts and "upgrade-insecure-requests" in csp \
    and "'unsafe-inline'" not in csp.split("script-src")[-1].split(";")[0]
check("F-08", "Production responses must carry HSTS and an upgraded CSP",
      "HSTS present, CSP has upgrade-insecure-requests and no inline script",
      f"hsts={hsts!r} csp={csp!r}", ok)

print()
print("=" * 78)
insecure = [r for r in results if not r[4]]
print(f"SUMMARY: {len(results)} checks, {len(results) - len(insecure)} secure, "
      f"{len(insecure)} INSECURE")
if insecure:
    for row in insecure:
        print(f"  - {row[0]} {row[1]}")
print("=" * 78)
