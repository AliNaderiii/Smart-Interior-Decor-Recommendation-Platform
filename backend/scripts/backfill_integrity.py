#!/usr/bin/env python3
"""Evaluate the catalog-integrity gate for every existing product (ADR-016).

Migration ``0007`` adds ``integrity_ok`` as NULL for legacy rows, which the
recommender treats as *eligible* so a deploy never goes dark. This script turns
NULL into a real verdict. Run it once after the migration and again whenever
``ai/catalog_integrity.py`` changes (``INTEGRITY_POLICY_VERSION``).

Usage::

    python scripts/backfill_integrity.py                   # stamp verdicts
    python scripts/backfill_integrity.py --strict          # production tier
    python scripts/backfill_integrity.py --unverify-failing
        # additionally set is_verified=False on failing rows so they land in
        # the admin review queue (recommended before a production data release)
    python scripts/backfill_integrity.py --dry-run

Idempotent; prints a per-reason summary. Rows carrying ``admin_override``
keep their forced eligibility unless ``--reset-overrides`` is passed.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from ai import catalog_integrity as policy  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.services import catalog_integrity as integrity  # noqa: E402


def run(*, strict: bool | None, unverify_failing: bool, reset_overrides: bool, dry_run: bool) -> dict:
    reasons: Counter = Counter()
    stats = Counter()
    with SessionLocal() as db:
        products = list(db.scalars(select(Product).order_by(Product.id)))
        index = integrity.image_index(db, products)
        for product in products:
            decision = integrity.evaluate(product, strict=strict, known_images=index)
            integrity.stamp(product, decision, keep_override=not reset_overrides)
            stats["evaluated"] += 1
            if product.integrity_ok:
                stats["eligible"] += 1
            else:
                stats["excluded"] += 1
                if unverify_failing and product.is_verified:
                    product.is_verified = False
                    stats["unverified"] += 1
            for code in decision["reasons"]:
                reasons[code] += 1
        if dry_run:
            db.rollback()
        else:
            db.commit()
    return {
        "policy_version": policy.INTEGRITY_POLICY_VERSION,
        "strict": integrity.strict_mode() if strict is None else strict,
        "dry_run": dry_run,
        **dict(stats),
        "reason_counts": dict(sorted(reasons.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--unverify-failing", action="store_true")
    parser.add_argument("--reset-overrides", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = run(
        strict=True if args.strict else None,
        unverify_failing=args.unverify_failing,
        reset_overrides=args.reset_overrides,
        dry_run=args.dry_run,
    )
    for key, value in result.items():
        if key != "reason_counts":
            print(f"{key:<16}: {value}")
    if result["reason_counts"]:
        print("reasons:")
        for code, n in result["reason_counts"].items():
            print(f"  {n:>5}  {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
