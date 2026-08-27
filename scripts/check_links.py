#!/usr/bin/env python3
"""Acceptance-criteria link validation: every product's seller_link must
answer HTTP 200 (2xx/3xx accepted after redirects).

Usage (from repo root, backend venv active):
    python scripts/check_links.py [--fail-fast] [--report docs/reports/links.json]
                                  [--detailed-report OUT.json]
                                  [--delay SECONDS] [--retries N]

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

import os
import sys
import time
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)  # so the default sqlite:///./decor.sqlite3 resolves correctly

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.services.link_checker import check_url_detailed  # noqa: E402


def _arg_value(flag: str, default: str | None = None) -> str | None:
    if flag in sys.argv:
        return sys.argv[sys.argv.index(flag) + 1]
    return default


def main() -> int:
    fail_fast = "--fail-fast" in sys.argv
    report_path = _arg_value("--report")
    detailed_path = _arg_value("--detailed-report")
    delay = float(_arg_value("--delay", "1.0"))
    retries = int(_arg_value("--retries", "1"))

    db = SessionLocal()
    try:
        products = list(db.scalars(select(Product).where(Product.seller_link != "")))
        print(f"checking {len(products)} product links… "
              f"(delay={delay}s, retries={retries} on network errors)")
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
        compact = (f"{len(products) - dead}/{len(products)} valid | "
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
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
