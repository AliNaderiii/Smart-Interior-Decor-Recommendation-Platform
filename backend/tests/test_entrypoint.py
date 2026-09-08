"""ADR-017 · the container entrypoint is the deploy on a shell-less PaaS.

What must hold:

* the ``CATALOG_BOOTSTRAP`` grammar is strict — a typo refuses the boot
  (exit 2) instead of silently doing nothing;
* ``replace@<label>`` runs **once per label per database**: the label is
  claimed in ``bootstrap_runs`` before anything is deleted, a repeat boot with
  the same label is a no-op, a failed load releases the claim;
* ``if-empty`` never touches a populated table;
* production refuses every loading mode, at configuration time and again in
  the step itself;
* the Dockerfile ``CMD`` is the entrypoint and the compose files keep their
  explicit commands (their contracts are tested elsewhere and unchanged).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models.bootstrap_run import ACTION_CATALOG_REPLACE, BootstrapRun
from app.models.product import Product
from scripts import entrypoint

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


@pytest.fixture()
def clean_bootstrap_runs():
    with SessionLocal() as db:
        db.execute(delete(BootstrapRun))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(delete(BootstrapRun))
        db.commit()


def _product_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(Product.id))) or 0


# ------------------------------------------------------------------ grammar

class TestModeGrammar:
    @pytest.mark.parametrize("raw", ["", None, "off", "none", "0", "false", "  off  "])
    def test_unset_and_off_spellings_mean_off(self, raw):
        assert entrypoint.parse_mode(raw).kind == "off"

    def test_if_empty(self):
        assert entrypoint.parse_mode("if-empty") == entrypoint.Mode("if-empty")

    @pytest.mark.parametrize("label", ["2026-09-08", "ticket-42", "v3.1_reseed", "A"])
    def test_replace_with_valid_label(self, label):
        mode = entrypoint.parse_mode(f"replace@{label}")
        assert (mode.kind, mode.label) == ("replace", label)
        assert str(mode) == f"replace@{label}"

    @pytest.mark.parametrize("raw", [
        "replace", "replace@", "replace@bad label", "replace@-x", "replace@" + "a" * 65,
        "always", "clear", "if_empty", "IF-EMPTY", "replace:2026",
    ])
    def test_anything_else_is_a_configuration_error(self, raw):
        with pytest.raises(entrypoint.BootstrapConfigError):
            entrypoint.parse_mode(raw)

    def test_configuration_error_exits_2_without_touching_the_database(self, monkeypatch):
        touched = []
        monkeypatch.setattr(entrypoint, "bootstrap", lambda mode: touched.append(mode))
        assert entrypoint.main(["--catalog", "always", "--no-server"]) == entrypoint.EXIT_CONFIG
        assert touched == []


class TestServerCommand:
    def test_default_honours_port_and_web_concurrency(self, monkeypatch):
        monkeypatch.setenv("PORT", "10000")
        monkeypatch.setenv("WEB_CONCURRENCY", "1")
        cmd = entrypoint.default_server_command()
        assert cmd[:2] == ["uvicorn", "app.main:app"]
        assert cmd[cmd.index("--port") + 1] == "10000"
        assert cmd[cmd.index("--workers") + 1] == "1"
        assert "--no-server-header" in cmd and "--proxy-headers" in cmd

    def test_default_without_platform_variables(self, monkeypatch):
        monkeypatch.delenv("PORT", raising=False)
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
        cmd = entrypoint.default_server_command()
        assert cmd[cmd.index("--port") + 1] == "8000"
        assert cmd[cmd.index("--workers") + 1] == "2"


# ------------------------------------------------------------- catalog step

class TestCatalogStep:
    def test_off_does_nothing(self, clean_bootstrap_runs):
        calls = []
        before = _product_count()
        report = entrypoint.catalog_step(entrypoint.Mode("off"), loader=lambda **kw: calls.append(kw))
        assert report["outcome"] == "off"
        assert calls == []
        assert _product_count() == before

    def test_if_empty_skips_a_populated_table(self, clean_bootstrap_runs):
        assert _product_count() > 0  # the session fixture seeds the catalog
        calls = []
        report = entrypoint.catalog_step(entrypoint.Mode("if-empty"), loader=lambda **kw: calls.append(kw))
        assert report["outcome"] == "skipped_nonempty"
        assert calls == []
        with SessionLocal() as db:
            assert db.scalar(select(func.count(BootstrapRun.id))) == 0

    def test_replace_claims_the_label_then_loads_then_records(self, clean_bootstrap_runs):
        seen: list[dict] = []

        def fake_loader(**kwargs):
            # By the time the loader runs the label must already be claimed —
            # that ordering is what makes a crash mid-load safe.
            with SessionLocal() as db:
                claim = db.scalar(select(BootstrapRun).where(BootstrapRun.label == "t-1"))
                assert claim is not None and claim.action == ACTION_CATALOG_REPLACE
                assert claim.detail.startswith("claimed;")
            seen.append(kwargs)
            return 150

        report = entrypoint.catalog_step(entrypoint.Mode("replace", "t-1"), loader=fake_loader)
        assert report["outcome"] == "replaced"
        assert seen == [{"clear": True, "expand_to": 150}]
        with SessionLocal() as db:
            run = db.scalar(select(BootstrapRun).where(BootstrapRun.label == "t-1"))
            assert "loaded 150 sample rows" in run.detail
            assert "deleted" in run.detail

    def test_replace_is_once_per_label(self, clean_bootstrap_runs):
        calls = []
        first = entrypoint.catalog_step(entrypoint.Mode("replace", "t-2"), loader=lambda **kw: calls.append(kw) or 150)
        second = entrypoint.catalog_step(entrypoint.Mode("replace", "t-2"), loader=lambda **kw: calls.append(kw) or 150)
        assert first["outcome"] == "replaced"
        assert second["outcome"] == "skipped_done"
        assert len(calls) == 1
        # a NEW label runs again — that is the operator's explicit intent
        third = entrypoint.catalog_step(entrypoint.Mode("replace", "t-3"), loader=lambda **kw: calls.append(kw) or 150)
        assert third["outcome"] == "replaced"
        assert len(calls) == 2

    def test_failed_replace_releases_the_label_so_the_next_boot_retries(self, clean_bootstrap_runs):
        def broken_loader(**kwargs):
            raise RuntimeError("dataset missing")

        with pytest.raises(RuntimeError, match="dataset missing"):
            entrypoint.catalog_step(entrypoint.Mode("replace", "t-4"), loader=broken_loader)
        with SessionLocal() as db:
            assert db.scalar(select(BootstrapRun).where(BootstrapRun.label == "t-4")) is None
        calls = []
        retry = entrypoint.catalog_step(entrypoint.Mode("replace", "t-4"), loader=lambda **kw: calls.append(kw) or 150)
        assert retry["outcome"] == "replaced" and len(calls) == 1

    def test_unlabelled_runs_never_collide_on_the_unique_label_index(self, clean_bootstrap_runs):
        from app.models.bootstrap_run import ACTION_CATALOG_IF_EMPTY

        with SessionLocal() as db:
            db.add_all([
                BootstrapRun(action=ACTION_CATALOG_IF_EMPTY, label=None, detail="first"),
                BootstrapRun(action=ACTION_CATALOG_IF_EMPTY, label=None, detail="second"),
            ])
            db.commit()  # NULL != NULL: two if-empty loads may both be recorded
            assert db.scalar(select(func.count(BootstrapRun.id))) == 2

    @pytest.mark.parametrize("mode", [entrypoint.Mode("if-empty"), entrypoint.Mode("replace", "prod-1")])
    def test_production_refuses_every_loading_mode(self, reset_settings, clean_bootstrap_runs, mode):
        reset_settings(APP_ENV="production")
        calls = []
        report = entrypoint.catalog_step(mode, loader=lambda **kw: calls.append(kw))
        assert report["outcome"] == "refused_production"
        assert calls == []
        with SessionLocal() as db:
            assert db.scalar(select(func.count(BootstrapRun.id))) == 0


# ------------------------------------------------------- configuration gate

def _prod(**overrides) -> Settings:
    base = dict(
        APP_ENV="production", SECRET_KEY="x" * 48,
        REDIS_URL="redis://localhost:6379/0", COOKIE_SECURE=True,
        FRONTEND_ORIGIN="https://app.example.com",
        FERNET_KEY="2xLmTPRPYxxLW8mM3jXfKcXo5G3iVYkYfQ2vYbFsC8Y=",
        STORAGE_BACKEND="s3", SEED_DEMO_ACCOUNTS=False,
        AI_PROVIDER="gemini", GEMINI_API_KEY="test-gemini-key-placeholder",
    )
    base.update(overrides)
    return Settings(**base)


class TestProductionConfiguration:
    def test_default_is_off_and_accepted(self):
        cfg = _prod()
        assert cfg.CATALOG_BOOTSTRAP == "off"
        cfg.validate_runtime()

    @pytest.mark.parametrize("value", ["if-empty", "replace@2026-09-08", "typo"])
    def test_any_loading_mode_refuses_to_boot_production(self, value):
        with pytest.raises(RuntimeError, match="CATALOG_BOOTSTRAP"):
            _prod(CATALOG_BOOTSTRAP=value).validate_runtime()


# -------------------------------------------------------------- image wiring

class TestImageWiring:
    def test_dockerfile_cmd_is_the_entrypoint(self):
        text = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
        cmd_lines = [ln for ln in text.splitlines() if ln.startswith("CMD ")]
        assert cmd_lines == ['CMD ["python", "scripts/entrypoint.py"]']
        assert "ENTRYPOINT" not in text  # compose `command:` overrides must keep working

    def test_entrypoint_is_not_excluded_from_the_build_context(self):
        ignore = (BACKEND / ".dockerignore").read_text(encoding="utf-8")
        assert "scripts" not in ignore

    def test_compose_overrides_keep_their_explicit_commands(self):
        import yaml

        base = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
        assert "alembic upgrade head" in base["services"]["backend"]["command"]
        dev = yaml.safe_load((REPO / "docker-compose.dev.yml").read_text(encoding="utf-8"))
        assert "load_realistic_products" in dev["services"]["backend"]["command"]


# ------------------------------------------------------- end-to-end (sqlite)

class TestEndToEnd:
    """The real script, as a subprocess, on a throwaway SQLite database —
    the closest a unit test gets to a container boot."""

    def _run(self, tmp_path, *args, env_extra=None):
        import os

        env = dict(os.environ)
        env.update({
            "DATABASE_URL": f"sqlite:///{tmp_path / 'boot.sqlite3'}",
            "APP_ENV": "development", "SEED_DEMO_ACCOUNTS": "true",
            "AI_PROVIDER": "mock", "EMBEDDING_BACKEND": "hash", "STORAGE_BACKEND": "local",
            "PAYMENT_PROVIDER": "mock", "REDIS_URL": "", "SECRET_KEY": "test-secret-key",
            "LOCAL_STORAGE_DIR": str(tmp_path / "storage"),
        })
        env.pop("CATALOG_BOOTSTRAP", None)
        env.update(env_extra or {})
        return subprocess.run(
            [sys.executable, "scripts/entrypoint.py", *args], cwd=BACKEND, env=env,
            capture_output=True, text=True, timeout=600,
        )

    def test_fresh_database_replace_then_redeploy_then_if_empty(self, tmp_path):
        import sqlite3

        first = self._run(tmp_path, "--no-server", env_extra={"CATALOG_BOOTSTRAP": "replace@e2e-1"})
        assert first.returncode == 0, first.stderr[-3000:]
        assert "schema at alembic head" in first.stderr
        assert "catalog replace@e2e-1: done" in first.stderr
        assert "evaluated 150, eligible 150" in first.stderr

        again = self._run(tmp_path, "--no-server", env_extra={"CATALOG_BOOTSTRAP": "replace@e2e-1"})
        assert again.returncode == 0, again.stderr[-3000:]
        assert "already applied" in again.stderr

        steady = self._run(tmp_path, "--no-server", env_extra={"CATALOG_BOOTSTRAP": "if-empty"})
        assert steady.returncode == 0, steady.stderr[-3000:]
        assert "products table has 150 rows; skipping" in steady.stderr

        con = sqlite3.connect(tmp_path / "boot.sqlite3")
        try:
            assert con.execute("select count(*) from products").fetchone()[0] == 150
            assert con.execute("select count(*) from users").fetchone()[0] == 3
            assert con.execute(
                "select count(*) from bootstrap_runs where label='e2e-1'"
            ).fetchone()[0] == 1
            assert con.execute(
                "select count(*) from products where integrity_ok is null"
            ).fetchone()[0] == 0
        finally:
            con.close()

    def test_fresh_database_if_empty_loads_once_and_records_it(self, tmp_path):
        import sqlite3

        first = self._run(tmp_path, "--no-server", env_extra={"CATALOG_BOOTSTRAP": "if-empty"})
        assert first.returncode == 0, first.stderr[-3000:]
        assert "catalog if-empty: table was empty; loaded 150 rows" in first.stderr

        second = self._run(tmp_path, "--no-server", env_extra={"CATALOG_BOOTSTRAP": "if-empty"})
        assert second.returncode == 0, second.stderr[-3000:]
        assert "products table has 150 rows; skipping" in second.stderr

        con = sqlite3.connect(tmp_path / "boot.sqlite3")
        try:
            assert con.execute("select count(*) from products").fetchone()[0] == 150
            rows = con.execute("select action, label from bootstrap_runs").fetchall()
            assert rows == [("catalog_if_empty", None)]
        finally:
            con.close()

    def test_custom_command_after_double_dash_is_exec_ed(self, tmp_path):
        proc = self._run(tmp_path, "--catalog", "off", "--", sys.executable, "-c", "print('served')")
        assert proc.returncode == 0, proc.stderr[-3000:]
        assert proc.stdout.strip().endswith("served")
