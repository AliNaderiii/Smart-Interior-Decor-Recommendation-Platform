"""Import a real seller catalog through the ADR-016 integrity gate (P4-ب item 2).

Usage (dry-run is the default — nothing is written until ``--yes``)::

    # 1) a seller file (CSV/JSON; template: --template > feed.csv)
    python scripts/import_catalog.py file --path feed.csv --seller nilper
    python scripts/import_catalog.py file --path feed.csv --seller nilper --yes

    # 2) Basalam Open API — public search, no token needed
    python scripts/import_catalog.py basalam --category rug --max-per-query 40
    python scripts/import_catalog.py basalam --yes --verify             # all categories
    BASALAM_TOKEN=... python scripts/import_catalog.py basalam --details  # + GET /v1/products/{id}
    BASALAM_TOKEN=... python scripts/import_catalog.py basalam --vendor 78910

    # what would happen, row by row
    python scripts/import_catalog.py file --path feed.csv --seller nilper --report out.json

    # is DATABASE_URL the database I think it is? (no rows read or written)
    python scripts/import_catalog.py --check-db

Before anything else the target database is checked (``app.db.preflight``):
a placeholder or unparsable ``DATABASE_URL``, a missing driver, an unreachable
host or a schema behind this code all stop the run with a one-line reason and
the fix — before Basalam is contacted and before a single row is read.

Every accepted row goes through: normalise → SSRF-guarded image download →
upload-grade validation + perceptual hash → vision ``detected_category`` →
embedding → integrity stamp. Rows are **not** verified unless ``--verify`` is
given AND the row is clean AND the vision check agreed with the declared
category; everything else lands in the admin review queue (``/admin/products``,
filter "pending").

Exit codes: 0 done (or dry-run), 1 nothing importable / gateway failure,
2 bad usage.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.catalog_import import pipeline  # noqa: E402
from app.services.catalog_import.adapters import basalam as basalam_adapter  # noqa: E402
from app.services.catalog_import.adapters import file as file_adapter  # noqa: E402
from app.services.catalog_import.contract import seller_source  # noqa: E402

logger = logging.getLogger("import_catalog")

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--template", action="store_true",
                        help="print the CSV template to stdout and exit")
    parser.add_argument("--check-db", action="store_true",
                        help="validate DATABASE_URL, connect once, print the target and exit")
    sub = parser.add_subparsers(dest="adapter")

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--yes", action="store_true", help="actually write (default: dry-run)")
        p.add_argument("--verify", action="store_true",
                       help="mark clean rows verified when the vision check agrees (default: review queue)")
        p.add_argument("--no-vision", action="store_true", help="skip the vision provider (rows stay unverified)")
        p.add_argument("--no-link-check", action="store_true", help="do not probe seller links")
        p.add_argument("--include-unavailable", action="store_true",
                       help="import rows the feed marks out of stock (default: skip)")
        p.add_argument("--image-mode", choices=("rehost", "link"), default=None,
                       help="rehost = copy to platform storage (default when S3 configured); link = keep seller URL")
        p.add_argument("--refresh-images", action="store_true",
                       help="re-download pictures even when the feed URL is unchanged")
        p.add_argument("--limit", type=int, default=None, help="stop after N accepted rows")
        p.add_argument("--report", type=Path, default=None, help="write the full JSON report here")
        p.add_argument("--image-timeout", type=float, default=30.0)

    f = sub.add_parser("file", help="CSV / JSON / JSONL seller feed")
    f.add_argument("--path", type=Path, required=True)
    f.add_argument("--seller", required=True, help="slug → source=feed:<slug> (e.g. nilper)")
    f.add_argument("--default-category", default=None,
                   help="taxonomy id used when a row has no category column")
    f.add_argument("--allow-local-images", action="store_true",
                   help="image_url may be a local file path (offline batches)")
    common(f)

    b = sub.add_parser("basalam", help="official Basalam Open API")
    b.add_argument("--category", action="append", default=None,
                   help="taxonomy category to search (repeatable; default: all seven)")
    b.add_argument("--query", action="append", default=None,
                   help="override search terms as category=term (repeatable)")
    b.add_argument("--vendor", default=None, help="vendor id → GET /v1/vendors/{id}/products (needs token)")
    b.add_argument("--vendor-identifier", default=None, help="restrict search to one vendor (filters.vendorIdentifier)")
    b.add_argument("--details", action="store_true", help="also GET /v1/products/{id} (needs token)")
    b.add_argument("--rows", type=int, default=48, help="search page size")
    b.add_argument("--max-per-query", type=int, default=100)
    b.add_argument("--use-packaging-dimensions", action="store_true",
                   help="fall back to packaging_dimensions when no product dimensions exist (box ≠ product)")
    b.add_argument("--dump-raw", type=Path, default=None,
                   help="write the first raw search response here (to confirm the envelope shape)")
    b.add_argument("--token", default=None, help="personal access token (or env BASALAM_TOKEN)")
    b.add_argument("--base-url", default=basalam_adapter.BASE_URL)
    common(b)
    return parser


def _options(args: argparse.Namespace) -> pipeline.ImportOptions:
    return pipeline.ImportOptions(
        dry_run=not args.yes,
        vision=not args.no_vision,
        verify=args.verify,
        check_links=not args.no_link_check,
        limit=args.limit,
        skip_unavailable=not args.include_unavailable,
        image_timeout=args.image_timeout,
        image_mode=args.image_mode,
        refresh_images=args.refresh_images,
    )


def _print_summary(report: pipeline.ImportReport) -> None:
    s = report.summary()
    mode = "DRY-RUN (nothing written)" if s["dry_run"] else "WRITTEN"
    print(f"\n== catalog import: {s['source']} — {mode}; integrity strict={s['strict']}")
    print(f"   rows: {s['total']}  created={s['created']} updated={s['updated']} "
          f"unchanged={s['unchanged']} rejected={s['rejected']} skipped={s['skipped']}")
    print(f"   eligible for recommendations: {s['eligible']}  excluded by integrity: "
          f"{s['excluded_by_integrity']}  verified: {s['verified']}  needs review: {s['needs_review']}")
    if s["category_mismatch"]:
        print(f"   !! image≠category on {s['category_mismatch']} rows (kept unverified, excluded)")
    if s["by_category"]:
        print("   by category: " + ", ".join(f"{k}={v}" for k, v in s["by_category"].items()))
    if s["integrity_reasons"]:
        print("   integrity reasons: " + ", ".join(f"{k}×{v}" for k, v in s["integrity_reasons"].items()))
    if s["rejection_codes"]:
        print("   rejections/skips: " + ", ".join(f"{k}×{v}" for k, v in s["rejection_codes"].items()))
    if s["external_image_origins"]:
        print("   !! pictures are served from seller origins (image_mode=link): add to IMAGE_EXTRA_ORIGINS → "
              + ",".join(s["external_image_origins"]))
    shown = 0
    for r in report.rows:
        if r.action in ("rejected", "skipped") and shown < 15:
            print(f"   - {r.action:8} {r.source_product_id or '?':>14}  {','.join(r.codes)}  {r.title_fa[:50]}")
            shown += 1


def check_database() -> int:
    """Preflight the configured database; print where the rows would go.

    Runs *before* ``app.db.session`` is imported (that module builds the engine
    at import time and would turn a pasted placeholder into a traceback).
    Returns ``EXIT_USAGE`` with the operator sentence on stderr when the
    target must not be used.
    """
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
    print(f"vision:   {_vision_summary(settings)}")
    return EXIT_OK


def _vision_summary(settings: Any) -> str:
    """One line the operator can read before spending inference: provider, model, key *state*.

    The key itself is never printed; a value that still carries a guide
    placeholder (``<…>`` or Persian text) is called out, because with a bad
    key every row would come back ``provider_error`` — honest, but a wasted run.
    """
    provider = settings.AI_PROVIDER
    if provider == "mock":
        return "mock (filename heuristic — rows can be imported but never auto-verified)"
    key = settings.GEMINI_API_KEY if provider == "gemini" else settings.OPENAI_API_KEY
    model = settings.GEMINI_MODEL if provider == "gemini" else settings.OPENAI_MODEL
    if not key:
        state = "key MISSING (rows would be flagged provider_error)"
    elif "<" in key or ">" in key or any("\u0600" <= ch <= "\u06ff" for ch in key):
        state = "key looks like a guide PLACEHOLDER — replace it"
    else:
        state = "key set"
    return f"{provider} model={model} {state}"


def run_file(args: argparse.Namespace) -> int:
    try:
        source = seller_source(args.seller)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if not args.path.exists():
        print(f"error: {args.path} does not exist", file=sys.stderr)
        return EXIT_USAGE
    if (code := check_database()) != EXIT_OK:
        return code
    from app.db.session import SessionLocal

    try:
        rows = list(file_adapter.iter_file(args.path))
    except (ValueError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {args.path}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if not rows:
        print("error: the feed has no rows", file=sys.stderr)
        return EXIT_FAILED
    if args.allow_local_images and args.image_mode != "rehost":
        print("error: --allow-local-images requires --image-mode rehost (a local path cannot be served)",
              file=sys.stderr)
        return EXIT_USAGE
    with SessionLocal() as db:
        try:
            report = pipeline.import_rows(
                db, rows, source=source, options=_options(args),
                default_category=args.default_category, allow_local_images=args.allow_local_images,
            )
        except Exception as exc:  # provider/config errors surface as a clean failure
            print(f"error: import aborted: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_FAILED
    return _finish(report, args)


def run_basalam(args: argparse.Namespace) -> int:
    token = args.token or os.environ.get("BASALAM_TOKEN") or None
    queries: dict[str, list[str]] | None = None
    if args.query:
        queries = {}
        for spec in args.query:
            if "=" not in spec:
                print(f"error: --query expects category=term, got {spec!r}", file=sys.stderr)
                return EXIT_USAGE
            cat, term = spec.split("=", 1)
            queries.setdefault(cat.strip(), []).append(term.strip())
    elif args.category:
        unknown = [c for c in args.category if c not in basalam_adapter.CATEGORY_QUERIES]
        if unknown:
            print(f"error: unknown category {unknown}; choose from "
                  f"{sorted(basalam_adapter.CATEGORY_QUERIES)}", file=sys.stderr)
            return EXIT_USAGE
        queries = {c: basalam_adapter.CATEGORY_QUERIES[c] for c in args.category}

    if (code := check_database()) != EXIT_OK:
        return code

    dumped = {"done": False}

    def on_raw(label: str, payload: object) -> None:
        if args.dump_raw and not dumped["done"]:
            args.dump_raw.write_text(json.dumps({"query": label, "response": payload}, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
            dumped["done"] = True
            print(f"raw response written to {args.dump_raw}")

    from app.db.session import SessionLocal

    try:
        with basalam_adapter.BasalamClient(token=token, base_url=args.base_url) as client:
            if args.vendor:
                rows_iter = basalam_adapter.iter_vendor(
                    client, args.vendor, use_packaging_dimensions=args.use_packaging_dimensions, on_raw=on_raw,
                )
            else:
                rows_iter = basalam_adapter.iter_search(
                    client, queries=queries, rows=args.rows, max_per_query=args.max_per_query,
                    vendor_identifier=args.vendor_identifier, details=args.details,
                    use_packaging_dimensions=args.use_packaging_dimensions, on_raw=on_raw,
                )
            rows = list(rows_iter)
    except basalam_adapter.BasalamError as exc:
        print(f"error: Basalam gateway: {exc}", file=sys.stderr)
        return EXIT_FAILED
    if not rows:
        print("error: Basalam returned no products (use --dump-raw to inspect the response)", file=sys.stderr)
        return EXIT_FAILED
    print(f"fetched {len(rows)} candidate products from Basalam")
    with SessionLocal() as db:
        try:
            report = pipeline.import_rows(db, rows, source=basalam_adapter.SOURCE, options=_options(args))
        except Exception as exc:
            print(f"error: import aborted: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_FAILED
    return _finish(report, args)


def _finish(report: pipeline.ImportReport, args: argparse.Namespace) -> int:
    _print_summary(report)
    if args.report:
        args.report.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, default=str),
                               encoding="utf-8")
        print(f"report written to {args.report}")
    if not report.accepted and report.rows:
        return EXIT_FAILED
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("alembic").setLevel(logging.WARNING)  # the preflight reads the revision only
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.template:
        sys.stdout.write(file_adapter.template_csv())
        return EXIT_OK
    if args.check_db:
        return check_database()
    if args.adapter == "file":
        return run_file(args)
    if args.adapter == "basalam":
        return run_basalam(args)
    parser.print_help()
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
