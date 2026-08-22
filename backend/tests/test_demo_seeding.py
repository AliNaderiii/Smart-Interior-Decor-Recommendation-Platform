"""Stage 03 · the top-priority regression: no predictable accounts in production.

Master Prompt 03 / IR-001 / blocker B-1. Baseline behaviour is recorded in
`docs/agent-reports/security-hardening-evidence/03-BEFORE-demo-seeding-probe.txt`:
three of three production seed runs created `admin@smartdecor.dev / Admin123!`.

These tests pin every lock on the gate independently, so removing any one of
them fails the suite rather than quietly restoring the vulnerability.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core import demo_seed
from app.core.config import Settings
from app.models.user import User

BACKEND = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------- unit-level gate

def test_production_refuses_even_with_explicit_opt_in(reset_settings):
    """The environment lock is not overridable by the opt-in flag."""
    reset_settings(APP_ENV="production", SEED_DEMO_ACCOUNTS=True)
    assert demo_seed.demo_seeding_allowed() is False


def test_production_strict_mode_raises_instead_of_silently_skipping(reset_settings):
    reset_settings(APP_ENV="production", SEED_DEMO_ACCOUNTS=True)
    with pytest.raises(demo_seed.DemoSeedRefused, match="production"):
        demo_seed.demo_seeding_allowed(strict=True)


def test_cli_enable_is_refused_in_production(reset_settings):
    reset_settings(APP_ENV="production", SEED_DEMO_ACCOUNTS=False)
    with pytest.raises(demo_seed.DemoSeedRefused):
        demo_seed.enable_for_this_process()


def test_development_without_opt_in_creates_nothing(reset_settings, db):
    """Default-off everywhere: silence is the safe default, not convenience."""
    reset_settings(APP_ENV="development", SEED_DEMO_ACCOUNTS=False)
    assert demo_seed.ensure_demo_accounts(db) == []


def test_development_with_opt_in_is_allowed(reset_settings):
    reset_settings(APP_ENV="development", SEED_DEMO_ACCOUNTS=True)
    assert demo_seed.demo_seeding_allowed() is True


def test_ensure_demo_accounts_returns_nothing_in_production(reset_settings, db):
    reset_settings(APP_ENV="production", SEED_DEMO_ACCOUNTS=True)
    before = db.scalar(select(User).where(User.email == "admin@smartdecor.dev"))
    created = demo_seed.ensure_demo_accounts(db)
    assert created == []
    # The pre-existing test-fixture admin must be untouched either way.
    after = db.scalar(select(User).where(User.email == "admin@smartdecor.dev"))
    assert (before is None) == (after is None)


# ------------------------------------------------------------- config fail-fast

def _prod(**overrides) -> Settings:
    base = dict(
        APP_ENV="production", SECRET_KEY="x" * 48,
        REDIS_URL="redis://localhost:6379/0", COOKIE_SECURE=True,
        FRONTEND_ORIGIN="https://app.example.com",
        FERNET_KEY="2xLmTPRPYxxLW8mM3jXfKcXo5G3iVYkYfQ2vYbFsC8Y=",
        STORAGE_BACKEND="s3", SEED_DEMO_ACCOUNTS=False,
    )
    base.update(overrides)
    return Settings(**base)


def test_production_boot_refuses_when_demo_seeding_requested():
    cfg = _prod(SEED_DEMO_ACCOUNTS=True)
    with pytest.raises(RuntimeError, match="SEED_DEMO_ACCOUNTS"):
        cfg.validate_runtime()


def test_production_boot_accepts_the_safe_default():
    _prod().validate_runtime()  # must not raise


# ---------------------------------------------------------- boot-time DB guard

def test_boot_guard_refuses_production_with_demo_rows(reset_settings, db):
    """Covers restored dumps and deployments made before this fix."""
    reset_settings(APP_ENV="production", REFUSE_DEMO_ACCOUNTS_IN_PRODUCTION=True)
    # The test database is seeded with the demo accounts on purpose
    # (SEED_DEMO_ACCOUNTS=true in conftest), which is exactly the situation the
    # guard exists to catch.
    assert demo_seed.find_demo_accounts(db)
    with pytest.raises(RuntimeError, match="predictable demo account"):
        demo_seed.assert_no_demo_accounts_in_production(db)


def test_boot_guard_is_a_no_op_outside_production(reset_settings, db):
    reset_settings(APP_ENV="development")
    demo_seed.assert_no_demo_accounts_in_production(db)  # must not raise


# ------------------------------------------------------- end-to-end, real seeder

def _run_seeder(tmp_path: Path, env_overrides: dict[str, str], argv: list[str]):
    # Stage 04 note: production no longer permits seeding a catalog with hash
    # embeddings (ai.embedding_service raises EmbeddingBackendError — see
    # docs/ai/model-versions.md). The documented deploy flow is "seed once at
    # deployment time (development profile or --from-json with committed real
    # vectors), serve in production", so this fixture pre-seeds the database in
    # development mode first. The production-mode invocation under test then
    # exercises the `--if-empty` steady state exactly as compose runs it.
    # The dev pre-seed never carries --seed-demo-accounts: the production
    # invocation must still be the one that refuses the flag.
    dev_argv = [a for a in argv if a != "--seed-demo-accounts"]
    dev_env = dict(os.environ)
    dev_env.update({
        "APP_ENV": "development",
        "AI_PROVIDER": "mock", "EMBEDDING_BACKEND": "hash",
        "STORAGE_BACKEND": "local", "PAYMENT_PROVIDER": "mock",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'seed.sqlite3'}",
        "LOCAL_STORAGE_DIR": str(tmp_path / "storage"),
    })
    dev_env.pop("SEED_DEMO_ACCOUNTS", None)
    subprocess.run(
        [sys.executable, *dev_argv], cwd=BACKEND, env=dev_env,
        capture_output=True, text=True, timeout=600,
    )
    env = dict(os.environ)
    env.update({
        "APP_ENV": "production", "SECRET_KEY": "p" * 48,
        "REDIS_URL": "redis://127.0.0.1:6399/15", "COOKIE_SECURE": "true",
        "FRONTEND_ORIGIN": "https://app.example.com",
        "AI_PROVIDER": "mock", "EMBEDDING_BACKEND": "hash",
        "STORAGE_BACKEND": "local", "PAYMENT_PROVIDER": "mock",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'seed.sqlite3'}",
        "LOCAL_STORAGE_DIR": str(tmp_path / "storage"),
    })
    env.pop("SEED_DEMO_ACCOUNTS", None)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, *argv], cwd=BACKEND, env=env,
        capture_output=True, text=True, timeout=600,
    )


def _demo_users(db_file: Path) -> list[str]:
    import sqlite3

    if not db_file.exists():
        return []
    con = sqlite3.connect(db_file)
    try:
        return [
            row[0] for row in con.execute(
                "select email from users where email like '%@smartdecor.dev'"
            )
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


@pytest.mark.parametrize("argv", [
    ["scripts/load_realistic_products.py", "--realistic", "--if-empty"],
    ["scripts/seed_products.py", "--if-empty"],
])
def test_seed_entrypoints_create_no_demo_users_in_production(tmp_path, argv):
    """The exact command `docker-compose.yml` runs on every backend start."""
    proc = _run_seeder(tmp_path, {}, argv)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert _demo_users(tmp_path / "seed.sqlite3") == []


@pytest.mark.parametrize("argv", [
    ["scripts/load_realistic_products.py", "--realistic", "--if-empty"],
    ["scripts/seed_products.py", "--if-empty"],
])
def test_seed_entrypoints_ignore_the_opt_in_in_production(tmp_path, argv):
    proc = _run_seeder(tmp_path, {"SEED_DEMO_ACCOUNTS": "true"}, argv)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert _demo_users(tmp_path / "seed.sqlite3") == []
    assert "Refusing to create demo/default accounts" in (proc.stderr + proc.stdout)


def test_seed_entrypoint_still_works_for_local_development(tmp_path):
    """Developer convenience must survive the fix — that is the whole point."""
    proc = _run_seeder(
        tmp_path,
        {"APP_ENV": "development", "COOKIE_SECURE": "false",
         "SEED_DEMO_ACCOUNTS": "true", "REDIS_URL": ""},
        ["scripts/load_realistic_products.py", "--realistic", "--if-empty"],
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert sorted(_demo_users(tmp_path / "seed.sqlite3")) == [
        "admin@smartdecor.dev", "demo@smartdecor.dev", "designer@smartdecor.dev",
    ]


def test_cli_flag_is_refused_in_production_subprocess(tmp_path):
    proc = _run_seeder(
        tmp_path, {},
        ["scripts/load_realistic_products.py", "--realistic", "--if-empty",
         "--seed-demo-accounts"],
    )
    assert proc.returncode != 0, "the CLI flag must be a hard error in production"
    assert "refused" in (proc.stderr + proc.stdout).lower()
    assert _demo_users(tmp_path / "seed.sqlite3") == []


# ------------------------------------------------------------- no leaked secrets

def test_credentials_live_in_exactly_one_module():
    """One place to audit. A second copy is how the first fix got undone."""
    literals = [f"{q}{pw}{q}"
                for pw in ("Admin123!", "Demo1234!", "Design123!")
                for q in ("'", '"')]
    candidates = list((BACKEND / "app").rglob("*.py"))
    candidates += list((BACKEND / "scripts").glob("*.py"))
    offenders = [
        str(path.relative_to(BACKEND))
        for path in candidates
        if path.name != "demo_seed.py"
        and any(lit in path.read_text(encoding="utf-8") for lit in literals)
    ]
    assert offenders == [], f"demo passwords duplicated in: {offenders}"
