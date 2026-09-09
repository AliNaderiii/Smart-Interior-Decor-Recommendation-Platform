#!/usr/bin/env python3
"""Container entrypoint — migrate, bootstrap the catalog, backfill, serve (ADR-017).

Why this exists
---------------
On a PaaS without a shell (Render free tier and similar) the *only* thing that
runs is the image's command: no pre-deploy hook, no console, and on some plans
not even an editable start command. Everything a deploy needs in order to be
healthy therefore has to live in the image and be safe to run on **every**
boot. This script is that path; ``backend/Dockerfile`` makes it the default
``CMD``. Compose files keep their explicit ``command:`` overrides, so their
behaviour is unchanged.

Steps (each idempotent, each logged with a ``[boot n/5]`` prefix):

1. ``settings.validate_runtime()`` — fail before touching the database.
2. ``alembic upgrade head`` in-process, then assert the database is at head.
   Serialised across replicas with a PostgreSQL advisory lock.
3. Catalog bootstrap, selected by ``CATALOG_BOOTSTRAP`` (or ``--catalog``):

   * ``off`` / unset — nothing (the production default).
   * ``if-empty`` — load the committed 150-row sample catalog when the
     products table is empty; skip otherwise. Repeatable.
   * ``replace@<label>`` — delete **every** product and load the sample
     catalog, **once per label per database**. The label is claimed in
     ``bootstrap_runs`` (unique) *before* anything is deleted, so a restart,
     a rollback or a second replica can never wipe the catalog twice.
     Recommendation cache entries (``rec:*``) are flushed afterwards.

   Both loading modes are refused under ``APP_ENV=production`` — the sample
   rows are ``source=synthetic-demo`` and the strict integrity gate would
   exclude them anyway (ADR-016). ``validate_runtime`` already refuses to boot
   production with the variable set; the check here is belt and braces.
4. Demo accounts — ``app.core.demo_seed.ensure_demo_accounts`` when
   ``SEED_DEMO_ACCOUNTS=true`` (never in production, same gate as always).
5. Integrity backfill — ``scripts/backfill_integrity.run`` stamps a verdict on
   every row (``price_stale`` moves with time, so re-evaluating per boot is a
   feature, not waste).

Then ``exec`` the server. Default::

    uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
            --workers ${WEB_CONCURRENCY:-2} --no-server-header --proxy-headers

Anything after ``--`` replaces that command; ``--no-server`` runs the steps
and exits (CI, rehearsals). Exit codes: 0 ok · 2 configuration error ·
1 a step failed (the container must not serve from a half-prepared database).

Rehearse locally::

    DATABASE_URL=sqlite:////tmp/x.sqlite3 APP_ENV=development \\
      python scripts/entrypoint.py --catalog replace@local --no-server
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

logger = logging.getLogger("entrypoint")

#: Arbitrary but fixed: every replica of this application takes the same
#: PostgreSQL advisory lock while it migrates and bootstraps.
BOOTSTRAP_LOCK_KEY = 728_162_017
#: ``replace@<label>`` labels: something an operator can type in a PaaS
#: dashboard and read back in a database (dates, ticket ids).
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SAMPLE_CATALOG_ROWS = 150
DEFAULT_SERVER = (
    "uvicorn", "app.main:app", "--host", "0.0.0.0",
    "--port", "{port}", "--workers", "{workers}", "--no-server-header", "--proxy-headers",
)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CONFIG = 2


class BootstrapConfigError(ValueError):
    """The operator asked for something this entrypoint does not understand."""


@dataclass(frozen=True)
class Mode:
    kind: Literal["off", "if-empty", "replace"]
    label: str | None = None

    def __str__(self) -> str:
        return f"replace@{self.label}" if self.kind == "replace" else self.kind


def parse_mode(raw: str | None) -> Mode:
    """``CATALOG_BOOTSTRAP`` grammar: ``off`` | ``if-empty`` | ``replace@<label>``.

    Empty/unset means ``off``. Anything else is a configuration error — a typo
    must surface as a refused boot, never as a silent no-op the operator
    mistakes for success.
    """
    value = (raw or "").strip()
    if value in ("", "off", "none", "0", "false"):
        return Mode("off")
    if value == "if-empty":
        return Mode("if-empty")
    if value.startswith("replace@"):
        label = value[len("replace@"):]
        if not LABEL_RE.match(label):
            raise BootstrapConfigError(
                f"CATALOG_BOOTSTRAP={value!r}: the label after 'replace@' must match "
                f"{LABEL_RE.pattern} (e.g. replace@2026-09-08 or replace@ticket-42)"
            )
        return Mode("replace", label)
    raise BootstrapConfigError(
        f"CATALOG_BOOTSTRAP={value!r} is not understood. Use 'off', 'if-empty' or "
        f"'replace@<label>' (see docs/DEPLOYMENT.md, 'PaaS without a shell')."
    )


def default_server_command() -> list[str]:
    port = os.environ.get("PORT", "").strip() or "8000"
    workers = os.environ.get("WEB_CONCURRENCY", "").strip() or "2"
    return [part.format(port=port, workers=workers) for part in DEFAULT_SERVER]


# --------------------------------------------------------------------------- steps

def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", force=True)
    logging.getLogger("alembic").setLevel(logging.INFO)
    # Plugin discovery chatter adds nothing to a deploy log.
    logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)


class _AdvisoryLock:
    """Serialise bootstrap across replicas (PostgreSQL only; SQLite has one writer)."""

    def __init__(self) -> None:
        self._conn = None

    def __enter__(self) -> _AdvisoryLock:
        from sqlalchemy import text

        from app.core.config import settings
        from app.db.session import engine

        if settings.is_postgres:
            self._conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
            self._conn.execute(text("SELECT pg_advisory_lock(CAST(:key AS bigint))"), {"key": BOOTSTRAP_LOCK_KEY})
            logger.info("[boot] advisory lock %d acquired", BOOTSTRAP_LOCK_KEY)
        return self

    def __exit__(self, *_exc) -> None:
        if self._conn is not None:
            from sqlalchemy import text

            try:
                self._conn.execute(text("SELECT pg_advisory_unlock(CAST(:key AS bigint))"), {"key": BOOTSTRAP_LOCK_KEY})
            finally:
                self._conn.close()
                self._conn = None


def run_migrations() -> str:
    """``alembic upgrade head`` in-process; returns the head revision.

    Raises ``RuntimeError`` when the database is not at head afterwards — a
    container that serves new code on an old schema is exactly the 500 this
    entrypoint exists to prevent.
    """
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from alembic import command
    from app.db.session import engine

    # No ini file on purpose: alembic.ini's fileConfig() would disable every
    # logger configured before it (including this one). env.py sets the URL
    # from Settings and imports the metadata itself.
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head() or ""
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current != head:
        raise RuntimeError(f"database is at alembic revision {current!r}, expected head {head!r}")
    return head


def _flush_recommendation_cache() -> int:
    """Best effort: cached /recommend payloads reference product ids that a
    replace just deleted. Never fails the boot."""
    try:
        from app.core.redis_client import get_redis

        redis = get_redis()
        keys = list(redis.scan_iter("rec:*"))
        if keys:
            redis.delete(*keys)
        return len(keys)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[boot] recommendation cache not flushed: %s", exc)
        return 0


def _source_breakdown(db) -> dict[str, int]:
    from sqlalchemy import func, select

    from app.models.product import Product

    rows = db.execute(select(Product.source, func.count(Product.id)).group_by(Product.source)).all()
    return {str(source or ""): int(n) for source, n in rows}


def catalog_step(mode: Mode, *, loader=None) -> dict:
    """Apply ``mode`` to the catalog. Returns a small report (also logged).

    ``loader(clear=..., expand_to=...)`` defaults to
    ``scripts.load_realistic_products.load`` and is injectable for tests.
    """
    from sqlalchemy import func, select
    from sqlalchemy.exc import IntegrityError

    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.models.bootstrap_run import (
        ACTION_CATALOG_IF_EMPTY,
        ACTION_CATALOG_REPLACE,
        BootstrapRun,
    )
    from app.models.product import Product

    if mode.kind == "off":
        logger.info("[boot 3/5] catalog bootstrap: off (CATALOG_BOOTSTRAP unset)")
        return {"mode": str(mode), "outcome": "off"}

    if settings.is_production:
        # ADR-016: the sample catalog is synthetic; production imports real
        # inventory. Fail-safe (serve, do not crash-loop) but impossible to miss.
        logger.critical(
            "[boot 3/5] REFUSING catalog bootstrap %s: APP_ENV=production. The sample "
            "catalog is source=synthetic-demo and the strict integrity gate excludes it; "
            "import a real seller feed instead (docs/DEPLOYMENT.md, V3).", mode,
        )
        return {"mode": str(mode), "outcome": "refused_production"}

    if loader is None:
        from scripts.load_realistic_products import load as loader

    with SessionLocal() as db:
        count = db.scalar(select(func.count(Product.id))) or 0
        before = _source_breakdown(db)

        if mode.kind == "if-empty":
            if count:
                logger.info("[boot 3/5] catalog if-empty: products table has %d rows; skipping", count)
                return {"mode": str(mode), "outcome": "skipped_nonempty", "count": count}
            # End the read transaction before the loader opens its own session:
            # SQLite would otherwise wait on our shared lock until it times out.
            db.commit()
            loaded = loader(if_empty=True, expand_to=SAMPLE_CATALOG_ROWS)
            db.add(BootstrapRun(action=ACTION_CATALOG_IF_EMPTY, label=None,
                                detail=f"products table was empty; loaded {loaded} sample rows"))
            db.commit()
            logger.info("[boot 3/5] catalog if-empty: table was empty; loaded %d rows", loaded)
            return {"mode": str(mode), "outcome": "loaded", "count": loaded}

        # replace@<label> — claim the label first, act second.
        existing = db.scalar(select(BootstrapRun).where(BootstrapRun.label == mode.label))
        if existing is not None:
            logger.info(
                "[boot 3/5] catalog %s already applied on %s (%s); skipping — choose a new "
                "label to replace again", mode, existing.created_at, existing.detail,
            )
            return {"mode": str(mode), "outcome": "skipped_done", "count": count}
        claim = BootstrapRun(action=ACTION_CATALOG_REPLACE, label=mode.label,
                             detail=f"claimed; before={before or {}}")
        db.add(claim)
        try:
            db.commit()
        except IntegrityError:  # another replica won the race
            db.rollback()
            logger.info("[boot 3/5] catalog %s claimed by another process; skipping", mode)
            return {"mode": str(mode), "outcome": "skipped_done", "count": count}

        logger.warning(
            "[boot 3/5] catalog %s: deleting %d product row(s) by source %s "
            "(dependent feedback/events/approvals cascade) and loading the sample catalog",
            mode, count, before or {},
        )
        try:
            # The loader deletes and inserts in ONE transaction of its own, so a
            # failure leaves the old catalog untouched — and must leave the label
            # unclaimed, so the next boot retries instead of silently skipping.
            loaded = loader(clear=True, expand_to=SAMPLE_CATALOG_ROWS)
        except BaseException:
            db.delete(claim)
            db.commit()
            raise
        flushed = _flush_recommendation_cache()
        claim.detail = (
            f"deleted {count} row(s) before={before or {}}; loaded {loaded} sample rows; "
            f"flushed {flushed} cached recommendation(s)"
        )[:500]
        db.commit()
        logger.info("[boot 3/5] catalog %s: done — %s", mode, claim.detail)
        return {"mode": str(mode), "outcome": "replaced", "deleted": count, "count": loaded}


def demo_accounts_step() -> list[str]:
    from app.core.config import settings

    if not settings.SEED_DEMO_ACCOUNTS:
        logger.info("[boot 4/5] demo accounts: SEED_DEMO_ACCOUNTS is false; nothing to do")
        return []
    from app.core.demo_seed import ensure_demo_accounts
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        created = ensure_demo_accounts(db)
        db.commit()
    logger.info("[boot 4/5] demo accounts: created %s", created or "none (already present)")
    return created


def backfill_step() -> dict:
    from scripts.backfill_integrity import run as backfill

    result = backfill(strict=None, unverify_failing=False, reset_overrides=False, dry_run=False)
    logger.info(
        "[boot 5/5] integrity backfill (policy %s, strict=%s): evaluated %d, eligible %d, excluded %d%s",
        result.get("policy_version"), result.get("strict"),
        result.get("evaluated", 0), result.get("eligible", 0), result.get("excluded", 0),
        f", reasons {result['reason_counts']}" if result.get("reason_counts") else "",
    )
    return result


def bootstrap(mode: Mode) -> dict:
    """Steps 2–5 under the advisory lock. Raises on failure."""
    report: dict = {"mode": str(mode)}
    with _AdvisoryLock():
        head = run_migrations()
        logger.info("[boot 2/5] schema at alembic head %s", head)
        report["head"] = head
        report["catalog"] = catalog_step(mode)
        report["demo_accounts"] = demo_accounts_step()
        report["backfill"] = backfill_step()
    return report


# ----------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    server: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, server = argv[:split], argv[split + 1:]

    parser = argparse.ArgumentParser(
        prog="entrypoint.py",
        description="Migrate, bootstrap the catalog, backfill integrity, then exec the server.",
    )
    parser.add_argument("--catalog", metavar="MODE",
                        help="override CATALOG_BOOTSTRAP: off | if-empty | replace@<label>")
    parser.add_argument("--no-server", action="store_true",
                        help="run the boot steps and exit instead of exec-ing the server")
    args = parser.parse_args(argv)

    _configure_logging()
    from app.core.config import settings

    try:
        mode = parse_mode(args.catalog if args.catalog is not None else settings.CATALOG_BOOTSTRAP)
    except BootstrapConfigError as exc:
        logger.critical("[boot] %s", exc)
        return EXIT_CONFIG

    logger.info("[boot 1/5] app_env=%s catalog_bootstrap=%s database=%s",
                settings.APP_ENV, mode, "postgresql" if settings.is_postgres else "sqlite")
    try:
        settings.validate_runtime()
    except RuntimeError as exc:
        logger.critical("[boot 1/5] configuration refused:\n%s", exc)
        return EXIT_CONFIG

    try:
        bootstrap(mode)
    except Exception as exc:
        logger.critical("[boot] FAILED — not starting the server: %s", exc, exc_info=True)
        return EXIT_FAILED

    if args.no_server:
        logger.info("[boot] --no-server: done")
        return EXIT_OK

    command = server or default_server_command()
    logger.info("[boot] exec: %s", " ".join(command))
    from app.db.session import engine

    engine.dispose()  # the server process opens its own pool
    sys.stdout.flush()
    sys.stderr.flush()
    os.execvp(command[0], command)
    return EXIT_FAILED  # pragma: no cover - execvp does not return


if __name__ == "__main__":
    raise SystemExit(main())
