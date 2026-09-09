"""Database preflight for the operator CLIs (P4-B·2b).

The first live catalog import failed with a SQLAlchemy traceback out of
``import app.db.session`` because ``DATABASE_URL`` still held the guide's
``<placeholder>``. These tests pin the two fixes: driver-less PostgreSQL URLs
(the form Render prints) are accepted, and every writer refuses a bad target
with a one-line reason + fix *before* touching the network or the database.
No test here opens a real PostgreSQL connection.
"""
from __future__ import annotations

import sqlite3

import pytest

from app.core.config import Settings, normalise_database_url, settings
from app.db import preflight
from app.db.preflight import DatabaseProblem, check_database_url, probe

PASTED_PLACEHOLDER = "<External Database URL از Render → Postgres → Connect>"
FAKE_PW = "not-a-real-credential-0000"


# ------------------------------------------------------------ normalisation

@pytest.mark.parametrize(("given", "expected"), [
    ("postgres://u:p@dpg-x.frankfurt-postgres.render.com/db",
     "postgresql+psycopg://u:p@dpg-x.frankfurt-postgres.render.com/db"),
    ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
    ("POSTGRESQL://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("  postgresql://u:p@host/db\n", "postgresql+psycopg://u:p@host/db"),
    ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("postgresql+psycopg2://u:p@host/db", "postgresql+psycopg2://u:p@host/db"),
    ("sqlite:///./decor.sqlite3", "sqlite:///./decor.sqlite3"),
    ("", ""),
])
def test_driverless_postgres_urls_are_routed_to_psycopg3(given, expected):
    assert normalise_database_url(given) == expected


def test_settings_normalise_the_render_style_url():
    """The dashboard prints postgres[ql]:// — to SQLAlchemy that means psycopg2, which is not installed."""
    cfg = Settings(DATABASE_URL="postgres://decor:x@dpg-abc.oregon-postgres.render.com/decor")
    assert cfg.DATABASE_URL == "postgresql+psycopg://decor:x@dpg-abc.oregon-postgres.render.com/decor"
    assert cfg.is_postgres is True


def test_settings_leave_sqlite_alone():
    assert Settings(DATABASE_URL="sqlite:///./x.sqlite3").DATABASE_URL == "sqlite:///./x.sqlite3"


# ------------------------------------------------------------- offline checks

def test_the_pasted_guide_placeholder_is_refused_without_echoing_it():
    with pytest.raises(DatabaseProblem) as err:
        check_database_url(PASTED_PLACEHOLDER)
    message = str(err.value)
    assert "placeholder" in message and "fix:" in message
    assert "Render" not in message.split("fix:")[0] or "External" in message
    assert "از" not in message  # the pasted value is never echoed


@pytest.mark.parametrize("value", ["<host>", "postgresql://user:...@host/db", "sqlite:///change-me.sqlite3"])
def test_other_template_fragments_are_refused(value):
    with pytest.raises(DatabaseProblem, match="placeholder"):
        check_database_url(value)


def test_empty_url_is_refused_with_the_render_hint():
    with pytest.raises(DatabaseProblem, match="empty") as err:
        check_database_url("   ")
    assert "External Database URL" in str(err.value)


def test_garbage_is_not_a_url():
    with pytest.raises(DatabaseProblem, match="not a SQLAlchemy URL"):
        check_database_url("dpg-abc.render.com decor")


def test_foreign_dialects_are_refused():
    with pytest.raises(DatabaseProblem, match="dialect 'mysql'"):
        check_database_url("mysql://u:p@h/d")


def test_missing_driver_names_the_lockfile():
    with pytest.raises(DatabaseProblem, match="driver") as err:
        check_database_url("postgresql+nosuchdriver://u:p@h/d")
    assert "requirements.lock.txt" in str(err.value)


def test_postgres_url_without_host_is_refused():
    pytest.importorskip("psycopg")
    with pytest.raises(DatabaseProblem, match="no host"):
        check_database_url("postgresql:///decor")


def test_valid_targets_are_described_without_the_password():
    pytest.importorskip("psycopg")
    target = check_database_url(f"postgres://decor:{FAKE_PW}@dpg-abc.frankfurt-postgres.render.com/decor")
    assert target.dialect == "postgresql" and target.driver == "psycopg"
    assert target.url.startswith("postgresql+psycopg://")
    assert FAKE_PW not in target.display and "***" in target.display
    local = check_database_url("sqlite:///./x.sqlite3")
    assert (local.dialect, local.driver) == ("sqlite", "pysqlite")


def test_redact_url_never_leaks():
    assert FAKE_PW not in preflight.redact_url(f"postgresql://u:{FAKE_PW}@h/d")
    assert preflight.redact_url(PASTED_PLACEHOLDER) == "<unparsable DATABASE_URL>"


# ------------------------------------------------------------------- probing

def test_probe_accepts_the_suite_database():
    """SQLite: create_all, no alembic_version but the ADR-016 columns → usable with revision ''.
    CI (PostgreSQL migrated by `alembic upgrade head` before pytest) → the head revision."""
    assert probe(settings.DATABASE_URL, require_schema=True) in ("", preflight.head_revision())


def test_probe_refuses_an_empty_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'empty.sqlite3'}"
    assert probe(url) == ""  # readable …
    with pytest.raises(DatabaseProblem, match="no schema"):  # … but not writable by the importer
        probe(url, require_schema=True)


def test_probe_refuses_a_database_behind_head(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version VALUES ('0001')")
    url = f"sqlite:///{path}"
    assert probe(url) == "0001"
    head = preflight.head_revision()
    assert head and head != "0001"
    with pytest.raises(DatabaseProblem) as err:
        probe(url, require_schema=True)
    assert "0001" in str(err.value) and head in str(err.value) and "alembic upgrade head" in str(err.value)


def test_probe_reports_a_refused_connection_without_the_password():
    pytest.importorskip("psycopg")
    url = f"postgresql://decor:{FAKE_PW}@127.0.0.1:1/decor"  # nothing listens on port 1
    with pytest.raises(DatabaseProblem, match="cannot connect") as err:
        probe(url, connect_timeout=3)
    message = str(err.value)
    assert FAKE_PW not in message and "***" in message
    assert "External" in message


def test_connect_hint_explains_compose_and_internal_hostnames():
    """A bare service name (compose `postgres`, Render's Internal URL) cannot resolve from a PC."""
    pytest.importorskip("psycopg")
    target = check_database_url(f"postgresql://decor:{FAKE_PW}@postgres:5432/decor")
    hint = preflight._connect_hint(target)
    assert "'postgres'" in hint and "External Database URL" in hint
    external = check_database_url(f"postgresql://decor:{FAKE_PW}@dpg-abc.frankfurt-postgres.render.com/decor")
    assert "External" in preflight._connect_hint(external) and "'dpg-" not in preflight._connect_hint(external)
    assert "writable" in preflight._connect_hint(check_database_url("sqlite:///./x.sqlite3"))


# ----------------------------------------------------------------------- CLI

class TestImportCatalogCli:
    def test_check_db_describes_the_target(self, capsys):
        from scripts import import_catalog

        assert import_catalog.main(["--check-db"]) == 0
        out = capsys.readouterr().out
        assert out.startswith("database: ") and "APP_ENV=" in out
        assert "sqlite:///" in out or "postgresql+psycopg://" in out
        assert "decor:decor@" not in out  # CI credentials are rendered as ***
        assert "vision:   mock" in out  # the suite runs on the keyword mock

    def test_check_db_reports_the_key_state_without_the_key(self, monkeypatch, capsys):
        from scripts import import_catalog

        monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "<کلید>")
        assert import_catalog.main(["--check-db"]) == 0
        out = capsys.readouterr().out
        assert "vision:   gemini model=" in out and "PLACEHOLDER" in out and "<کلید>" not in out
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "AIza-not-a-real-key-000000000000000000")
        import_catalog.main(["--check-db"])
        out = capsys.readouterr().out
        assert "key set" in out and "AIza" not in out
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
        import_catalog.main(["--check-db"])
        assert "key MISSING" in capsys.readouterr().out

    def test_placeholder_stops_before_basalam_is_contacted(self, monkeypatch, capsys):
        from app.services.catalog_import.adapters import basalam
        from scripts import import_catalog

        monkeypatch.setattr(settings, "DATABASE_URL", PASTED_PLACEHOLDER)
        monkeypatch.setattr(basalam, "BasalamClient",
                            lambda *a, **k: pytest.fail("the gateway must not be contacted"))
        assert import_catalog.main(["--check-db"]) == 2
        assert import_catalog.main(["basalam", "--category", "rug", "--image-mode", "link"]) == 2
        err = capsys.readouterr().err
        assert "placeholder" in err and "fix:" in err
        assert "Traceback" not in err and "از" not in err

    def test_placeholder_stops_the_file_adapter_too(self, monkeypatch, tmp_path, capsys):
        from app.services.catalog_import.adapters import file as file_adapter
        from scripts import import_catalog

        feed = tmp_path / "feed.csv"
        feed.write_text(file_adapter.template_csv(), encoding="utf-8")
        monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://decor:<password>@host/decor")
        assert import_catalog.main(["file", "--path", str(feed), "--seller", "x"]) == 2
        err = capsys.readouterr().err
        assert "placeholder" in err and "<password>" not in err
