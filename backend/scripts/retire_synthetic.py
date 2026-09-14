"""Operator CLI: retire the synthetic sample catalog once real rows exist.

Why a script and not ``DELETE FROM products WHERE source='synthetic-demo'``:

* ``feedback``, ``feedback_events``, ``client_approvals`` and moodboard items
  reference products with ``ON DELETE CASCADE`` — a hard delete silently
  erases the behavioural evidence (ADR-014) and the demo moodboards clients
  were shown. Retiring is therefore a **soft** operation by default: the row
  is *unverified* (``is_verified=False``), which is exactly what the admin
  "unverify" button does — the row leaves the recommendable set (Stage A
  requires ``is_verified``), stays visible in the admin catalog with its
  provenance badge, and every FK keeps pointing at something.
* ``--delete`` is available for a staging reset, and refuses to run while any
  moodboard or share link still references a target row unless ``--force``.
* The synthetic rows are the *only* thing standing between the live demo
  and the ad's «اعتبار همهٔ لینک‌ها»: their seller links are retailer home
  pages, not product pages. This script is the last step of the P4-B cut-over
  and it will not run while a category would be left with fewer than
  ``--min-real`` recommendable real rows (default 3 = ``results.min_results``)
  — the whole point of the cut-over is that nothing gets thinner.

Dry-run is the default. Nothing is written until you pass ``--yes``.

    # 0. where would this write? (never prints the password)
    python scripts/retire_synthetic.py --check-db

    # 1. plan: what would be retired, per category, and what remains
    python scripts/retire_synthetic.py

    # 2. do it (soft): unverify, audit row per run, cache flush
    python scripts/retire_synthetic.py --yes --report C:\\Users\\alina\\Downloads\\retire.json

    # staging reset only
    python scripts/retire_synthetic.py --delete --yes

Selection = :func:`ai.catalog_integrity.is_synthetic` (``source`` in
``{synthetic-demo, perf}`` or the realistic-dataset marker in
``extraction_raw``) — the same predicate the production integrity gate uses,
so the script and the gate can never disagree about what "synthetic" means.
``--source`` narrows it further (repeatable).

Exit codes: 0 done (or dry-run), 1 refused by the coverage guard,
2 bad usage / database preflight failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai import catalog_integrity as policy  # noqa: E402

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2

def check_database() -> int:
    """Preflight the configured database *before* ``app.db.session`` is imported."""
    from app.core.config import settings
    from app.db.preflight import DatabaseProblem, check_database_url, probe

    try:
        target = check_database_url(settings.DATABASE_URL)
        revision = probe(settings.DATABASE_URL, require_schema=True)
    except DatabaseProblem as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(f"database: {target.display} ({target.dialect}/{target.driver}, "
          f"alembic {revision or 'create_all'}, APP_ENV={settings.APP_ENV})")
    return EXIT_OK


def select_targets(rows: list[Any], sources: tuple[str, ...] | list[str]) -> list[Any]:
    """Synthetic rows (gate predicate), optionally narrowed to ``sources``."""
    wanted = {s.strip().lower() for s in sources if s.strip()}
    out = []
    for row in rows:
        if not policy.is_synthetic(row):
            continue
        if wanted and (row.source or "").strip().lower() not in wanted:
            continue
        out.append(row)
    return out


def _recommendable(row: Any) -> bool:
    """Same predicate as Stage A minus the budget window."""
    return bool(row.is_verified) and row.integrity_ok is not False and row.room_type == "living_room"


def plan(rows: list[Any], targets: list[Any], categories: list[str], min_real: int) -> dict[str, Any]:
    """Per-category before/after picture + the coverage verdict."""
    target_ids = {t.id for t in targets}
    per_cat: dict[str, dict[str, int]] = {c: {"synthetic": 0, "synthetic_verified": 0,
                                              "real_total": 0, "real_recommendable": 0}
                                          for c in categories}
    for row in rows:
        bucket = per_cat.setdefault(row.category, {"synthetic": 0, "synthetic_verified": 0,
                                                    "real_total": 0, "real_recommendable": 0})
        if row.id in target_ids:
            bucket["synthetic"] += 1
            if row.is_verified:
                bucket["synthetic_verified"] += 1
        else:
            bucket["real_total"] += 1
            if _recommendable(row):
                bucket["real_recommendable"] += 1
    thin = sorted(c for c in categories if per_cat[c]["real_recommendable"] < min_real)
    return {
        "targets": len(targets),
        "targets_by_source": dict(Counter((t.source or "") for t in targets)),
        "per_category": per_cat,
        "min_real": min_real,
        "thin_categories": thin,
        "ok": not thin,
    }


def _references(db: Any, target_ids: set[str]) -> dict[str, int]:
    """How many moodboards / share-link approvals still point at the targets."""
    from sqlalchemy import select

    from app.models.moodboard import Moodboard
    from app.models.project import ClientApproval

    boards = 0
    for items in db.scalars(select(Moodboard.items)):
        if any(str(i.get("product_id")) in target_ids for i in (items or []) if isinstance(i, dict)):
            boards += 1
    approvals = sum(
        1 for pid in db.scalars(select(ClientApproval.product_id)) if pid in target_ids
    )
    return {"moodboards": boards, "client_approvals": approvals}


def _print_plan(report: dict[str, Any], *, delete: bool) -> None:
    verb = "DELETE" if delete else "unverify"
    print(f"synthetic rows selected: {report['targets']}  by source: {report['targets_by_source']}")
    print(f"{'category':<14}{'synthetic':>10}{'(verified)':>11}{'real':>7}{'real-recommendable':>20}")
    for cat, b in sorted(report["per_category"].items()):
        flag = "  <-- thin" if cat in report["thin_categories"] else ""
        print(f"{cat:<14}{b['synthetic']:>10}{b['synthetic_verified']:>11}{b['real_total']:>7}"
              f"{b['real_recommendable']:>20}{flag}")
    if report["thin_categories"]:
        print(f"\nREFUSED: {', '.join(report['thin_categories'])} would be left with fewer than "
              f"{report['min_real']} recommendable real rows. Import real rows for those categories "
              f"first (scripts/import_catalog.py), or narrow with --category, or lower --min-real "
              f"if that is a deliberate decision.")
    else:
        print(f"\nplan: {verb} {report['targets']} synthetic rows; every category keeps >= "
              f"{report['min_real']} recommendable real rows.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check-db", action="store_true", help="preflight the database and exit")
    parser.add_argument("--source", action="append", default=[],
                        help="narrow to this source value (repeatable; default: every synthetic row)")
    parser.add_argument("--category", action="append", default=[],
                        help="only retire synthetic rows of this category (repeatable)")
    parser.add_argument("--min-real", type=int, default=None,
                        help="refuse if a category would keep fewer recommendable real rows "
                             "(default: results.min_results from the recommender config)")
    parser.add_argument("--delete", action="store_true",
                        help="hard-delete instead of unverify (staging reset; cascades feedback/approvals)")
    parser.add_argument("--force", action="store_true",
                        help="with --delete: proceed even if moodboards/approvals reference the rows")
    parser.add_argument("--reason", default="P4-B cut-over: synthetic sample retired after real import",
                        help="recorded on the audit row")
    parser.add_argument("--report", type=Path, help="write the JSON plan/result here")
    parser.add_argument("--yes", action="store_true", help="actually write (default: dry-run)")
    args = parser.parse_args(argv)

    if args.check_db:
        return check_database()
    if args.force and not args.delete:
        parser.error("--force only makes sense with --delete")

    from sqlalchemy import select

    from app.core.config import settings
    from app.db.preflight import DatabaseProblem, check_database_url
    from app.db.session import SessionLocal
    from app.models import audit_log as actions
    from app.models.product import CATEGORIES, Product
    from app.services import audit
    from app.services.recommender import MIN_RESULTS, flush_recommendation_cache

    try:
        target = check_database_url(settings.DATABASE_URL)
    except DatabaseProblem as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    min_real = MIN_RESULTS if args.min_real is None else args.min_real
    categories = [c for c in CATEGORIES if not args.category or c in args.category]
    unknown = sorted(set(args.category) - set(CATEGORIES))
    if unknown:
        parser.error(f"unknown category {unknown}; choose from {sorted(CATEGORIES)}")

    started = datetime.now(timezone.utc)
    with SessionLocal() as db:
        rows = list(db.scalars(select(Product).order_by(Product.category, Product.id)))
        targets = [t for t in select_targets(rows, args.source) if t.category in categories]
        report = plan(rows, targets, categories, min_real)
        report.update({
            "database": target.display,
            "app_env": settings.APP_ENV,
            "mode": "delete" if args.delete else "unverify",
            "dry_run": not args.yes,
            "started_at": started.isoformat(),
        })
        print(f"database: {target.display} (APP_ENV={settings.APP_ENV})")
        _print_plan(report, delete=args.delete)

        refs = _references(db, {t.id for t in targets}) if args.delete else None
        if refs is not None:
            report["references"] = refs
            print(f"references: {refs['moodboards']} moodboard(s), {refs['client_approvals']} client approval(s)")

        code = EXIT_OK
        if not report["ok"]:
            code = EXIT_REFUSED
        elif args.delete and refs and any(refs.values()) and not args.force:
            print("REFUSED: rows are still referenced (moodboards/approvals cascade on delete). "
                  "Prefer the default unverify, or pass --force for a staging reset.")
            code = EXIT_REFUSED
        elif not args.yes:
            print("dry-run: nothing written. Re-run with --yes to apply.")
        else:
            changed = 0
            for row in targets:
                if args.delete:
                    db.delete(row)
                    changed += 1
                elif row.is_verified:
                    row.is_verified = False
                    changed += 1
            audit.record(
                db, actions.ACTION_SYNTHETIC_RETIRE if args.delete else actions.ACTION_PRODUCT_UNVERIFY,
                detail=f"retire_synthetic mode={report['mode']} rows={changed} "
                       f"categories={','.join(categories)} reason={args.reason}"[:500],
                commit=False,
            )
            db.commit()
            flushed = flush_recommendation_cache()
            report.update({"changed": changed, "cache_flushed": flushed,
                           "finished_at": datetime.now(timezone.utc).isoformat()})
            print(f"done: {report['mode']} {changed} rows; recommendation cache entries flushed: {flushed}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
                               encoding="utf-8")
        print(f"report written: {args.report}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
