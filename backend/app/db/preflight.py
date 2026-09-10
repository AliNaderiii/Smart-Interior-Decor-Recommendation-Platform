"""Operator-facing database preflight for the CLI tools.

``app.db.session`` builds the engine at import time, so a wrong
``DATABASE_URL`` used to surface as a SQLAlchemy traceback out of a module
import — and the first live catalog import (P4-B·2) died exactly there, with
the guide's ``<placeholder>`` still in the variable. Scripts that write to a
database call :func:`probe` **before** importing the session module and print
:class:`DatabaseProblem` verbatim: one sentence naming the problem, one naming
the fix, never the credential.

The offline checks are free; :func:`probe` opens one connection
(``SELECT 1``), reads the Alembic revision and — for the writers — refuses a
database whose schema is behind the code, so an import can never fail
half-way on a missing column.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError, NoSuchModuleError

from app.core.config import normalise_database_url

#: Fragments that cannot occur in a real connection string but do occur in
#: every guide template (``<…>``, ``...``, ``change-me``). Persian guide text
#: pasted verbatim is caught by the Arabic-script check in
#: :func:`_placeholder_marker`.
PLACEHOLDER_MARKERS = ("<", ">", "…", "...", "change-me", "changeme")

#: A column every ADR-016 database has; its absence means "never migrated".
_SCHEMA_TABLE, _SCHEMA_COLUMN = "products", "source_product_id"

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REDACTED = "***"


class DatabaseProblem(RuntimeError):
    """A DATABASE_URL that must not be used. ``str()`` is the operator message."""

    def __init__(self, problem: str, fix: str):
        super().__init__(f"{problem}\n  fix: {fix}")
        self.problem = problem
        self.fix = fix


@dataclass(frozen=True)
class DatabaseTarget:
    #: Normalised URL (driver-less PostgreSQL routed to psycopg 3).
    url: str
    #: Password-free rendering, safe to print and to log.
    display: str
    dialect: str  # postgresql | sqlite
    driver: str


def redact_url(url: str) -> str:
    """Render ``url`` with the password hidden; an unparsable string is not echoed at all."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except (ArgumentError, ValueError):
        return "<unparsable DATABASE_URL>"


def _placeholder_marker(value: str) -> str | None:
    for marker in PLACEHOLDER_MARKERS:
        if marker in value.lower():
            return marker
    if any("\u0600" <= ch <= "\u06ff" for ch in value):
        return "Persian text"
    return None


def check_database_url(url: str) -> DatabaseTarget:
    """Validate ``url`` offline; raise :class:`DatabaseProblem` with an actionable message.

    The value itself is never echoed — a half-edited template can still carry
    the real password next to the placeholder.
    """
    value = normalise_database_url(url or "")
    if not value:
        raise DatabaseProblem(
            "DATABASE_URL is empty.",
            "set it to the target database — for a Render database copy the External Database URL "
            "(Dashboard → your Postgres → Connect → External) into the same terminal session; "
            "for a local rehearsal use sqlite:///./rehearsal.sqlite3",
        )
    marker = _placeholder_marker(value)
    if marker is not None:
        raise DatabaseProblem(
            f"DATABASE_URL still contains a placeholder from the guide ({marker!r} found) — "
            "nothing was contacted.",
            "replace the whole <…> fragment with the real connection string (it starts with "
            "postgresql:// or sqlite:///); never paste the real string into chat or the repo",
        )
    try:
        parsed: URL = make_url(value)
    except ArgumentError:
        raise DatabaseProblem(
            "DATABASE_URL is not a SQLAlchemy URL.",
            "expected scheme://user:password@host:port/database — copy the External Database URL "
            "from the Render dashboard, or sqlite:///./file.sqlite3 for a local rehearsal",
        ) from None
    backend = parsed.get_backend_name()
    if backend not in ("postgresql", "sqlite"):
        raise DatabaseProblem(
            f"DATABASE_URL uses dialect {backend!r}; this project runs on PostgreSQL 16 (+pgvector) "
            "or SQLite.",
            "use postgresql://… (Render / docker-compose) or sqlite:///… (local rehearsal)",
        )
    try:
        dialect = parsed.get_dialect()
        dialect.import_dbapi()
    except (NoSuchModuleError, ImportError) as exc:
        raise DatabaseProblem(
            f"the database driver for {parsed.drivername!r} is not installed ({exc}).",
            "run `pip install -r requirements.lock.txt` inside the backend virtualenv "
            "(psycopg[binary] ships Windows wheels), or write the URL as postgresql+psycopg://…",
        ) from None
    if backend == "postgresql" and not parsed.host:
        raise DatabaseProblem(
            "DATABASE_URL has no host.",
            "the External Database URL looks like postgresql://user:password@dpg-….render.com/dbname",
        )
    return DatabaseTarget(
        url=value,
        display=parsed.render_as_string(hide_password=True),
        dialect=backend,
        driver=dialect.driver,
    )


def head_revision() -> str:
    """The repository's Alembic head (no ini file: env.py sets the URL itself)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head() or ""


def _connect_hint(target: DatabaseTarget) -> str:
    if target.dialect == "sqlite":
        return "check that the directory exists and is writable"
    host = make_url(target.url).host or ""
    if host and "." not in host and host not in ("localhost",):
        return (
            f"host {host!r} has no domain: that is a docker-compose service name or Render's "
            "*Internal* Database URL, neither of which resolves from your PC — use the External "
            "Database URL (Dashboard → Postgres → Connect → External)"
        )
    return (
        "check that the URL is the *External* one (the Internal URL only works inside Render), "
        "that the database is not suspended, and that your network allows outbound TCP 5432"
    )


def _safe_error(exc: BaseException, target: DatabaseTarget) -> str:
    """First line of a driver error, with the password scrubbed should a driver ever echo it."""
    text_ = str(exc).strip()
    first = text_.splitlines()[0] if text_ else ""
    password = make_url(target.url).password
    if password:
        first = first.replace(password, REDACTED)
    return f"{type(exc).__name__}: {first[:200]}"


def probe(url: str, *, require_schema: bool = False, connect_timeout: int = 10) -> str:
    """Connect once and return the Alembic revision (``""`` when the table is absent).

    ``require_schema=True`` (the writers) additionally refuses a database whose
    revision is behind this checkout's head, or that has no ``alembic_version``
    **and** lacks the ADR-016 columns (never migrated). A ``create_all``
    database with the columns (tests, local rehearsals) passes with an empty
    revision. Raises :class:`DatabaseProblem` for every refusal.
    """
    target = check_database_url(url)
    connect_args: dict[str, object] = (
        {"connect_timeout": connect_timeout} if target.dialect == "postgresql"
        else {"check_same_thread": False}
    )
    engine = create_engine(target.url, pool_pre_ping=True, connect_args=connect_args)
    try:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                from alembic.runtime.migration import MigrationContext

                current = MigrationContext.configure(conn).get_current_revision() or ""
                inspector = inspect(conn)
                columns = (
                    {c["name"] for c in inspector.get_columns(_SCHEMA_TABLE)}
                    if inspector.has_table(_SCHEMA_TABLE) else set()
                )
        except Exception as exc:  # driver errors differ per backend; the sentence is what matters
            raise DatabaseProblem(
                f"cannot connect to {target.display}: {_safe_error(exc, target)}",
                _connect_hint(target),
            ) from None
    finally:
        engine.dispose()

    if require_schema:
        head = head_revision()
        if current and current != head:
            raise DatabaseProblem(
                f"{target.display} is at Alembic revision {current}, this code expects {head}.",
                "migrate first — the Render entrypoint runs `alembic upgrade head` on every boot "
                "(deploy the merged main and wait for Live); locally run `alembic upgrade head` "
                "with the same DATABASE_URL — then re-run the import",
            )
        if not current and _SCHEMA_COLUMN not in columns:
            raise DatabaseProblem(
                f"{target.display} has no schema (no alembic_version and no {_SCHEMA_TABLE} table "
                "with the ADR-016 columns).",
                "run `alembic upgrade head` with the same DATABASE_URL first",
            )
    return current
