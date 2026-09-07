#!/usr/bin/env python3
"""Catalog-integrity audit — the CI/ops gate for ADR-016.

Runs ``ai.catalog_integrity`` over every product in the configured database
(or over a JSON catalog file, before it is imported) and reports, per category
and per reason code, how many rows are excluded from recommendations.

Exit status (so CI can gate on it):

* ``0`` — no VERIFIED row fails the enforced tier;
* ``1`` — at least one verified row fails (the engine would serve it if the
  runtime gate did not exist), or ``--strict`` was requested and a verified
  row fails the production tier (synthetic, duplicate photo, shallow link,
  stale price …).

Usage::

    python scripts/audit_catalog.py                    # DB, enforcement = APP_ENV
    python scripts/audit_catalog.py --strict           # production tier
    python scripts/audit_catalog.py --json             # machine-readable report
    python scripts/audit_catalog.py --check-images     # also HEAD every image URL
    python scripts/audit_catalog.py --file datasets/products_realistic_150.json

``--check-images`` needs egress and is deliberately opt-in (the CI backend job
has no business depending on a CDN); the catalog-import workflow runs it on the
operator's machine before a data release.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai import catalog_integrity as policy  # noqa: E402


def _image_reachable(url: str, timeout: float = 10.0) -> bool:
    """HEAD (GET fallback) with the SSRF-guarded fetcher's redirect policy."""
    import httpx

    from app.core.url_safety import UnsafeUrl, validate_public_url

    try:
        target = validate_public_url(url, resolve=True, field="image_url")
    except UnsafeUrl:
        return False
    try:
        with httpx.Client(follow_redirects=False, timeout=timeout) as client:
            for _ in range(5):
                resp = client.head(target)
                if resp.status_code in (405, 403, 501):
                    resp = client.get(target)
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location", "")
                    if not location:
                        return False
                    try:
                        target = validate_public_url(
                            str(httpx.URL(target).join(location)), resolve=True, field="image_url redirect"
                        )
                    except UnsafeUrl:
                        return False
                    continue
                return 200 <= resp.status_code < 300
    except httpx.HTTPError:
        return False
    return False


def _rows_from_file(path: Path) -> list[dict[str, Any]]:
    """Adapt a catalog JSON (importer/realistic schema) to product-like dicts."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["items"] if isinstance(data, dict) and "items" in data else data
    out: list[dict[str, Any]] = []
    for row in rows:
        dims = row.get("dimensions_cm") or {}
        out.append({
            "id": row.get("id"),
            "title": row.get("title_en") or row.get("title") or "",
            "title_fa": row.get("title_fa", ""),
            "category": row.get("category"),
            "price_toman": row.get("price_toman", 0),
            "image_url": row.get("image_url", ""),
            "image_phash": row.get("image_phash"),
            "seller_link": row.get("seller_link", ""),
            "link_status": row.get("link_status"),
            "materials": row.get("material_tags") or row.get("materials") or [],
            "width_cm": row.get("width_cm", dims.get("length", 0)),
            "depth_cm": row.get("depth_cm", dims.get("width", 0)),
            "height_cm": row.get("height_cm", dims.get("height", 0)),
            "price_checked_at": None,
            "source": row.get("source") or ("synthetic-demo" if row.get("dataset_notice") else "feed"),
            "extraction_raw": {"detected_category": row.get("detected_category") or row.get("category")},
            "is_verified": True,
        })
    return out


def audit(rows: list[Any], *, strict: bool, check_images: bool = False) -> dict[str, Any]:
    known: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        key = policy.image_key(policy._get(r, "image_url"), policy._get(r, "image_phash"))
        if key:
            known[key].add(str(policy._get(r, "id")))

    image_cache: dict[str, bool] = {}
    per_category: dict[str, Counter] = defaultdict(Counter)
    reasons: Counter = Counter()
    advisories: Counter = Counter()
    failing: list[dict[str, Any]] = []
    for r in rows:
        observed: list[str] = []
        url = str(policy._get(r, "image_url") or "")
        if check_images and url:
            if url not in image_cache:
                image_cache[url] = _image_reachable(url)
            if not image_cache[url]:
                observed.append("image_unreachable")
        decision = policy.integrity_decision(r, strict=strict, known_images=known, observed=observed)
        category = str(policy._get(r, "category"))
        verified = bool(policy._get(r, "is_verified"))
        per_category[category]["total"] += 1
        if verified:
            per_category[category]["verified"] += 1
            per_category[category]["eligible" if decision["ok"] else "excluded"] += 1
        for code in decision["reasons"]:
            reasons[code] += 1
        for code in decision["advisories"]:
            advisories[code] += 1
        if verified and not decision["ok"]:
            failing.append({
                "id": policy._get(r, "id"),
                "category": category,
                "title_fa": policy._get(r, "title_fa"),
                "reasons": decision["reasons"],
            })
    return {
        "policy_version": policy.INTEGRITY_POLICY_VERSION,
        "strict": strict,
        "check_images": check_images,
        "rows": len(rows),
        "verified_failing": len(failing),
        "by_category": {c: dict(v) for c, v in sorted(per_category.items())},
        "reason_counts": dict(sorted(reasons.items())),
        "advisory_counts": dict(sorted(advisories.items())),
        "failing": failing,
    }


def _print_human(report: dict[str, Any]) -> None:
    mode = "STRICT (production tier)" if report["strict"] else "truth tier only (dev/CI)"
    print(f"catalog integrity audit — policy {report['policy_version']} — {mode}")
    print(f"rows: {report['rows']}   verified rows failing: {report['verified_failing']}")
    print()
    print(f"{'category':<14}{'total':>7}{'verified':>10}{'eligible':>10}{'excluded':>10}")
    for cat, v in report["by_category"].items():
        print(f"{cat:<14}{v.get('total', 0):>7}{v.get('verified', 0):>10}{v.get('eligible', 0):>10}{v.get('excluded', 0):>10}")
    print()
    if report["reason_counts"]:
        print("blocking reasons:")
        for code, n in report["reason_counts"].items():
            print(f"  {n:>5}  {code:<26} {policy.INTEGRITY_REASON_TEXT.get(code, {}).get('en', '')}")
    if report["advisory_counts"]:
        print("advisories (would block in production):")
        for code, n in report["advisory_counts"].items():
            print(f"  {n:>5}  {code:<26} {policy.INTEGRITY_REASON_TEXT.get(code, {}).get('en', '')}")
    if report["failing"]:
        print()
        print("first failing verified rows:")
        for row in report["failing"][:15]:
            print(f"  - {row['id']} [{row['category']}] {row['title_fa']!r}: {', '.join(row['reasons'])}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strict", action="store_true", help="enforce the production tier regardless of APP_ENV")
    parser.add_argument("--json", action="store_true", help="print the JSON report instead of the table")
    parser.add_argument("--check-images", action="store_true", help="HEAD every image URL (needs egress)")
    parser.add_argument("--file", type=Path, help="audit a catalog JSON file instead of the database")
    args = parser.parse_args(argv)

    if args.file:
        rows: list[Any] = _rows_from_file(args.file)
        strict = args.strict
    else:
        from sqlalchemy import select

        from app.db.session import SessionLocal
        from app.models.product import Product
        from app.services.catalog_integrity import strict_mode

        strict = args.strict or strict_mode()
        with SessionLocal() as db:
            rows = list(db.scalars(select(Product).order_by(Product.category, Product.id)))
            report = audit(rows, strict=strict, check_images=args.check_images)
    if args.file:
        report = audit(rows, strict=strict, check_images=args.check_images)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(report)
    return 1 if report["verified_failing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
