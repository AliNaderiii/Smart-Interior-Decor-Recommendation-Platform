"""The test suite refuses settings inherited from an operator's shell (P4-B·2i).

``tests/conftest.py`` fills the environment with ``os.environ.setdefault``,
so a value already exported in the shell wins. CI relies on that to point the
suite at its PostgreSQL service (``decor_test``). The same rule made an
importer rehearsal shell dangerous: after dot-sourcing the rehearsal profile
(``DATABASE_URL=sqlite:///./import_rehearsal.sqlite3``, ``AI_PROVIDER=gemini``
with a real key) a plain ``pytest`` created tables in the rehearsal database,
seeded 100 synthetic products and three demo accounts into it, deleted every
``source=basalam`` row it held (the importer tests' cleanup fixture does
that on purpose — on a *test* database) and sent the fixtures' images to the
real vision provider, whose verdict on a flat-colour PNG then failed a test
that had nothing to do with the code under test. Pointed at the live
``DATABASE_URL`` instead of the rehearsal copy, the same run would have
deleted the sold catalog's imported rows.

So the suite checks, before any fixture runs, that an inherited setting
cannot make a test touch a real system: the database *name* must contain
``test``, the vision provider must be ``mock``, the object store ``local``,
and a Redis (the suite runs ``FLUSHALL`` before every test) must be local.
Pure function over a mapping, no application import — a safety check must
not depend on the settings object it is judging. ``conftest.pytest_configure``
turns a non-empty verdict into ``pytest.UsageError`` (exit code 4) with the
fix on the next line; ``PYTEST_ACCEPT_SHELL_ENV=1`` runs with the shell's
values on purpose.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

#: Export (any non-empty value) to run the suite with the shell's settings deliberately.
OVERRIDE_VAR = "PYTEST_ACCEPT_SHELL_ENV"

#: What the suite uses when nothing is inherited (mirrors ``conftest.py``).
SUITE_DATABASE = "sqlite:///./test_decor.sqlite3"

#: The settings this module judges (``conftest.py`` fills the rest with defaults).
SUITE_VARS = ("DATABASE_URL", "AI_PROVIDER", "STORAGE_BACKEND", "REDIS_URL")

_UNPARSABLE = "<unparsable DATABASE_URL>"


def redact(url: str) -> str:
    """``scheme://user:***@host/db`` — a value that does not parse is not echoed at all."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except (ArgumentError, ValueError):
        return _UNPARSABLE


def database_name(url: str) -> str | None:
    """Last component of the database part: ``decor_test``, ``test_decor.sqlite3``.

    ``""`` for an in-memory ``sqlite://``; ``None`` when the URL does not
    parse. Only the *name* is judged — a directory called ``tests`` must not
    vouch for a file called ``import_rehearsal.sqlite3``.
    """
    try:
        database = make_url(url).database
    except (ArgumentError, ValueError):
        return None
    if not database:
        return ""
    return re.split(r"[\\/]", database)[-1]


def shell_env_hazards(environ: Mapping[str, str]) -> list[str]:
    """One sentence per inherited setting the suite must not run with; empty means safe."""
    if environ.get(OVERRIDE_VAR):
        return []
    hazards: list[str] = []

    url = environ.get("DATABASE_URL")
    if url is not None:
        name = database_name(url)
        if not url.strip():
            hazards.append("DATABASE_URL is exported but empty — the suite cannot open a database "
                           "called ''; unset it to use the suite's own file")
        elif name is None:
            hazards.append("DATABASE_URL is not a SQLAlchemy URL (the value is not echoed)")
        elif name and "test" not in name.lower():
            hazards.append(
                f"DATABASE_URL={redact(url)} — the database name {name!r} does not contain 'test'; "
                "the suite creates tables there, seeds 100 synthetic products and 3 demo accounts, "
                "and deletes every source=basalam row"
            )

    provider = environ.get("AI_PROVIDER")
    if provider and provider != "mock":
        hazards.append(f"AI_PROVIDER={provider} — tests would send their fixture images to the real "
                       "vision provider and spend the key's quota")

    storage = environ.get("STORAGE_BACKEND")
    if storage and storage != "local":
        hazards.append(f"STORAGE_BACKEND={storage} — tests would upload their fixtures to the real "
                       "object store")

    redis_url = environ.get("REDIS_URL")
    if redis_url and _is_remote(redis_url):
        hazards.append(f"REDIS_URL={redact(redis_url)} — the suite runs FLUSHALL before every test; "
                       "a shared Redis would lose its sessions, rate limits and caches")
    return hazards


def _is_remote(url: str) -> bool:
    """A host with a domain that is not loopback: a managed Redis, not the CI service or compose."""
    host = (urlsplit(url).hostname or "").lower()
    return "." in host and host not in ("127.0.0.1", "localhost")


def refusal_message(hazards: list[str]) -> str:
    """The operator-facing text: what was inherited, what it would do, how to fix it."""
    return (
        "refusing to run the test suite with settings inherited from the shell:\n  - "
        + "\n  - ".join(hazards)
        + "\n  fix: run pytest in a fresh terminal, or drop the variables first — PowerShell: "
        "Remove-Item Env:DATABASE_URL, Env:AI_PROVIDER, Env:STORAGE_BACKEND, Env:REDIS_URL "
        "-ErrorAction SilentlyContinue; bash: unset DATABASE_URL AI_PROVIDER STORAGE_BACKEND "
        "REDIS_URL. The suite then uses "
        f"{SUITE_DATABASE} and the mock provider. CI's decor_test passes because its name "
        f"contains 'test'. To run with these values on purpose export {OVERRIDE_VAR}=1."
    )
