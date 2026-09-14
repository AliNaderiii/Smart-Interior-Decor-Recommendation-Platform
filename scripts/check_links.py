#!/usr/bin/env python3
"""Acceptance-criteria link validation: every product's seller_link must
answer HTTP 200 (2xx/3xx accepted after redirects).

Usage (from repo root, backend venv active):
    python scripts/check_links.py [--fail-fast] [--report docs/reports/links.json]
                                  [--detailed-report OUT.json]
                                  [--delay SECONDS] [--retries N]
                                  [--source NAME[,NAME…]] [--exclude-synthetic]
                                  [--verified-only] [--min-links N]
                                  [--file backend/seed_data/products_real_links.json]

P4-B·3 (cut-over to real rows): the acceptance criterion is about the links a
shopper is actually shown, so the selection can be narrowed to real rows —
``--exclude-synthetic`` drops the sample catalog (the integrity gate's
``is_synthetic`` predicate: ``source`` in ``{synthetic-demo, perf}`` or the
realistic-dataset marker), ``--source basalam`` keeps one feed, and
``--verified-only`` keeps what the recommender may return. ``--min-links N``
fails the run (exit 2) when fewer rows were selected than expected, so a CI
job that "passes" because the catalog was empty cannot happen silently.

``--file`` reads the rows from a seller-feed JSON (the export written by
``backend/scripts/export_real_links.py`` — verified, non-synthetic rows of the
live catalog) instead of a database: no schema, no image fetch, no vision —
only the seller links are probed. That is what CI runs; ``seller_link_ok`` is
not persisted in this mode (the JSON reports are the evidence).

Stage 2 (T-2.5): ``--detailed-report`` writes the full evidence record
(per-link classification ok/redirect/blocked/dead/unsafe/error, HTTP status,
latency, redirect chain) consumed by docs/reports/seller_links.md. ``--delay``
is the polite per-request pause (default 1.0 s — the catalog's sellers are a
handful of domains and hammering them classifies YOU as a bot). ``--retries``
re-probes only network-level failures (classification "error"), never
"blocked" (a bot wall answered; retrying is impolite and changes nothing).

Prints a per-domain summary, optionally writes a JSON report, and exits
non-zero if any link is dead.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[1] / "backend"
ORIGINAL_CWD = Path.cwd()
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)  # so the default sqlite:///./decor.sqlite3 resolves correctly

from ai import catalog_integrity as policy  # noqa: E402
from app.services.link_checker import check_url_detailed  # noqa: E402


def _arg_value(flag: str, default: str | None = None) -> str | None:
    if flag in sys.argv:
        return sys.argv[sys.argv.index(flag) + 1]
    return default


def select_products(rows, *, sources: set[str], exclude_synthetic: bool, verified_only: bool) -> list:
    """Apply the operator's selection to the rows that carry a seller link."""
    out = []
    for p in rows:
        if not p.seller_link:
            continue
        if sources and (p.source or "").strip().lower() not in sources:
            continue
        if exclude_synthetic and policy.is_synthetic(p):
            continue
        if verified_only and not p.is_verified:
            continue
        out.append(p)
    return out


def rows_from_file(path: Path) -> list:
    """Seller-feed JSON (``{"items": [...]}`` or a list) → row objects with the
    attributes the checker reads. Exported rows are verified real rows by
    construction; ``source`` falls back to the seller name."""
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise SystemExit(f"{path}: expected a JSON list or {{\"items\": [...]}}")
    rows = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        rows.append(SimpleNamespace(
            id=str(raw.get("source_product_id") or raw.get("id") or ""),
            category=raw.get("category"),
            seller_link=str(raw.get("seller_link") or "").strip(),
            source=str(raw.get("source") or raw.get("seller_name") or "feed"),
            is_verified=bool(raw.get("is_verified", True)),
            extraction_raw=raw.get("extraction_raw") or {},
        ))
    return rows


def main() -> int:
    fail_fast = "--fail-fast" in sys.argv
    report_path = _arg_value("--report")
    detailed_path = _arg_value("--detailed-report")
    delay = float(_arg_value("--delay", "1.0"))
    retries = int(_arg_value("--retries", "1"))
    sources = {s.strip().lower() for s in (_arg_value("--source", "") or "").split(",") if s.strip()}
    exclude_synthetic = "--exclude-synthetic" in sys.argv
    verified_only = "--verified-only" in sys.argv
    min_links = int(_arg_value("--min-links", "0"))
    file_arg = _arg_value("--file")

    db = None
    if file_arg:
        # The script chdir()s into backend/ at import; resolve a relative
        # --file against the operator's original directory first, then the
        # repo root, so both `scripts/check_links.py --file backend/seed_data/x.json`
        # (repo root) and `--file seed_data/x.json` (from backend/) work.
        file_path = Path(file_arg)
        if not file_path.is_absolute():
            for base in (ORIGINAL_CWD, BACKEND.parent, BACKEND):
                if (base / file_arg).exists():
                    file_path = base / file_arg
                    break
        if not file_path.exists():
            raise SystemExit(f"--file {file_arg}: not found")
        rows = rows_from_file(file_path)
        origin = f"file {file_path.name}"
    else:
        from sqlalchemy import select

        from app.db.session import SessionLocal
        from app.models.product import Product

        db = SessionLocal()
        rows = list(db.scalars(select(Product).where(Product.seller_link != "")))
        origin = "database"
    try:
        products = select_products(rows, sources=sources, exclude_synthetic=exclude_synthetic,
                                   verified_only=verified_only)
        selection = (f"{origin}; source={sorted(sources) or 'any'} "
                     f"exclude_synthetic={exclude_synthetic} verified_only={verified_only}")
        print(f"checking {len(products)} of {len(rows)} product links… ({selection}; "
              f"delay={delay}s, retries={retries} on network errors)")
        if len(products) < min_links:
            print(f"::error title=link-liveness-selection::only {len(products)} links selected, "
                  f"expected at least {min_links} — the catalog this job was pointed at is not "
                  f"loaded ({selection})")
            return 2
        unique_urls = sorted({p.seller_link for p in products})
        detailed: dict[str, dict] = {}
        results: dict[str, bool] = {}
        for i, url in enumerate(unique_urls):
            r = check_url_detailed(url)
            attempt = 0
            while r.classification == "error" and attempt < retries:
                attempt += 1
                time.sleep(max(delay, 1.0) * attempt)
                r = check_url_detailed(url)
            detailed[url] = r.as_dict() | {"retries_used": attempt}
            results[url] = r.ok
            status = r.http_status if r.http_status is not None else "---"
            lat = f"{r.latency_ms:.0f}ms" if r.latency_ms is not None else "-"
            print(f"  [{'OK ' if r.ok else r.classification.upper()[:4]:<4}] "
                  f"{status} {lat:>7} {url}")
            if not r.ok and fail_fast:
                return 1
            if delay and i < len(unique_urls) - 1:
                time.sleep(delay)

        dead = 0
        for p in products:
            ok = results[p.seller_link]
            p.seller_link_ok = ok
            if not ok:
                dead += 1
        if db is not None:
            db.commit()

        domains = Counter(u.split("/")[2] for u in unique_urls)
        by_class = Counter(d["classification"] for d in detailed.values())
        print(f"\ndomains: {dict(domains)}")
        print(f"classifications: {dict(by_class)}")
        print(f"result : {len(products) - dead}/{len(products)} links valid")

        # Annotation-readable summary + the not-ok URL list (CI artifacts are
        # not downloadable from the supervising sandbox; annotations are).
        not_ok = [f"{d['classification']}:{u}" for u, d in detailed.items()
                  if not d["ok"]]
        compact = (f"{len(products) - dead}/{len(products)} valid | {selection} | "
                   f"classes={dict(by_class)} | domains={dict(domains)}")
        print(f"::notice title=link-liveness-summary::{compact[:2000]}")
        if not_ok:
            print(f"::notice title=link-liveness-not-ok::{' ;; '.join(not_ok)[:2000]}")

        import datetime
        import json

        if report_path:
            rp = Path(report_path)
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(json.dumps({
                "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "selection": {"origin": origin, "source": sorted(sources),
                              "exclude_synthetic": exclude_synthetic,
                              "verified_only": verified_only, "rows_with_link": len(rows)},
                "total": len(products),
                "valid": len(products) - dead,
                "dead": dead,
                "pass": dead == 0,
                "urls": {url: ok for url, ok in results.items()},
            }, indent=2))
            print(f"report : {rp}")

        if detailed_path:
            dp = Path(detailed_path)
            dp.parent.mkdir(parents=True, exist_ok=True)
            dp.write_text(json.dumps({
                "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "delay_seconds": delay,
                "retries_on_error": retries,
                "total_products": len(products),
                "unique_urls": len(unique_urls),
                "classifications": dict(by_class),
                "links": detailed,
            }, indent=2, ensure_ascii=False))
            print(f"detailed: {dp}")

        return 1 if dead else 0
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
