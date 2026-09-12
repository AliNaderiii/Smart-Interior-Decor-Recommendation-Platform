"""The suite refuses settings inherited from an operator's shell (P4-B·2i).

A rehearsal profile (``DATABASE_URL=sqlite:///./import_rehearsal.sqlite3``,
``AI_PROVIDER=gemini`` with a real key) left in the PowerShell session made a
plain ``pytest`` seed synthetic rows into the importer's rehearsal database,
delete its imported rows and send fixture images to the real vision provider —
and one CLI test failed on the provider's verdict, not on the code. These
tests pin the guard: what is refused, what CI and compose still pass, that no
credential is echoed, and that the refusal really happens before any fixture
runs (a subprocess ``pytest`` exits 4 with the fix in its output).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import _env_guard as guard

BACKEND = Path(__file__).resolve().parents[1]
FAKE_PW = "not-a-real-credential-0000"

CI_ENV = {
    "DATABASE_URL": "postgresql+psycopg://decor:decor@localhost:5432/decor_test",
    "TEST_DATABASE_URL": "postgresql+psycopg://decor:decor@localhost:5432/decor_pgvector_test",
    "REDIS_URL": "redis://localhost:6379/1",
    "TEST_REDIS_URL": "redis://localhost:6379/9",
    "AI_PROVIDER": "mock",
    "EMBEDDING_BACKEND": "hash",
    "STORAGE_BACKEND": "local",
    "APP_ENV": "test",
}
COMPOSE_ENV = {
    "DATABASE_URL": "postgresql+psycopg://decor:decor@postgres:5432/decor_test",
    "REDIS_URL": "redis://redis:6379/1",
    "AI_PROVIDER": "mock",
}
REHEARSAL_ENV = {
    "DATABASE_URL": "sqlite:///./import_rehearsal.sqlite3",
    "APP_ENV": "development",
    "AI_PROVIDER": "gemini",
    "GEMINI_API_KEY": "AIza-not-a-real-key-000000000000000000",
    "EMBEDDING_BACKEND": "hash",
}


# --------------------------------------------------------------- what passes

@pytest.mark.parametrize("environ", [{}, CI_ENV, COMPOSE_ENV, {"DATABASE_URL": "sqlite://"}],
                         ids=["fresh shell", "github actions", "docker compose test overlay", "in-memory"])
def test_the_suite_s_own_targets_are_not_hazards(environ):
    assert guard.shell_env_hazards(environ) == []


def test_the_override_variable_accepts_everything():
    assert guard.shell_env_hazards({**REHEARSAL_ENV, guard.OVERRIDE_VAR: "1"}) == []
    assert guard.shell_env_hazards({**REHEARSAL_ENV, guard.OVERRIDE_VAR: ""})  # empty = not set


# -------------------------------------------------------------- what refuses

def test_the_rehearsal_profile_is_refused_for_the_database_and_the_provider():
    hazards = guard.shell_env_hazards(REHEARSAL_ENV)
    assert len(hazards) == 2
    assert "import_rehearsal.sqlite3" in hazards[0] and "does not contain 'test'" in hazards[0]
    assert "source=basalam" in hazards[0]  # says what the suite would do there
    assert hazards[1].startswith("AI_PROVIDER=gemini") and "quota" in hazards[1]


def test_a_live_postgres_url_is_refused_without_its_password():
    url = f"postgresql://neondb_owner:{FAKE_PW}@ep-abc-pooler.eu-west-2.aws.neon.tech/neondb?sslmode=require"
    hazards = guard.shell_env_hazards({"DATABASE_URL": url})
    assert len(hazards) == 1 and "'neondb'" in hazards[0]
    assert FAKE_PW not in hazards[0] and "neondb_owner:***@" in hazards[0]
    message = guard.refusal_message(hazards)
    assert FAKE_PW not in message and "Remove-Item Env:DATABASE_URL" in message and "unset DATABASE_URL" in message
    assert guard.OVERRIDE_VAR in message and guard.SUITE_DATABASE in message


def test_only_the_file_name_is_judged_not_its_directory():
    url = r"sqlite:///C:\Users\alina\tests\import_rehearsal.sqlite3"
    assert guard.database_name(url) == "import_rehearsal.sqlite3"
    assert guard.shell_env_hazards({"DATABASE_URL": url})
    assert guard.shell_env_hazards({"DATABASE_URL": "sqlite:///C:/work/rehearsal/test_decor.sqlite3"}) == []


@pytest.mark.parametrize(("value", "fragment"), [
    ("", "exported but empty"),
    ("   ", "exported but empty"),
    ("<External Database URL از Render>", "not a SQLAlchemy URL"),
])
def test_unusable_values_are_refused_without_being_echoed(value, fragment):
    hazards = guard.shell_env_hazards({"DATABASE_URL": value})
    assert len(hazards) == 1 and fragment in hazards[0]
    assert "از" not in hazards[0] and "<" not in hazards[0]


def test_remote_redis_and_s3_are_refused_local_ones_pass():
    assert guard.shell_env_hazards({"REDIS_URL": "redis://127.0.0.1:6399/15"}) == []
    assert guard.shell_env_hazards({"REDIS_URL": "redis://localhost:6379/2"}) == []
    remote = guard.shell_env_hazards({"REDIS_URL": f"rediss://default:{FAKE_PW}@usw1-x.upstash.io:6379"})
    assert len(remote) == 1 and "FLUSHALL" in remote[0] and FAKE_PW not in remote[0]
    assert guard.shell_env_hazards({"STORAGE_BACKEND": "s3"})[0].startswith("STORAGE_BACKEND=s3")
    assert guard.shell_env_hazards({"STORAGE_BACKEND": "local"}) == []


def test_redact_never_leaks_and_never_echoes_garbage():
    assert FAKE_PW not in guard.redact(f"postgresql://u:{FAKE_PW}@h/d")
    assert guard.redact("<External Database URL از Render>") == "<unparsable DATABASE_URL>"


# ---------------------------------------------------- the real pytest refuses

def test_pytest_itself_exits_4_before_touching_the_inherited_database(tmp_path):
    """End to end: a subprocess ``pytest`` with the rehearsal profile stops in
    ``pytest_configure`` — exit code 4 (usage error), the fix in the output,
    and the rehearsal database file never created."""
    rehearsal = tmp_path / "import_rehearsal.sqlite3"
    env = {k: v for k, v in os.environ.items() if k not in guard.SUITE_VARS and k != guard.OVERRIDE_VAR}
    env.update(REHEARSAL_ENV, DATABASE_URL=f"sqlite:///{rehearsal}", PYTHONUTF8="1")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_env_guard.py", "-q", "-o", "addopts=",
         "-p", "no:cacheprovider", "--collect-only"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=600,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 4, output
    assert "refusing to run the test suite" in output and "import_rehearsal.sqlite3" in output
    assert "AI_PROVIDER=gemini" in output and "Remove-Item Env:DATABASE_URL" in output
    assert "AIza" not in output  # the key is never part of the message
    assert not rehearsal.exists()  # nothing connected, nothing created
