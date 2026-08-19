#!/usr/bin/env python3
"""Acceptance-criteria link validation: every product's seller_link must
answer HTTP 200 (2xx/3xx accepted after redirects).

Usage (from repo root, backend venv active):
    python scripts/check_links.py [--fail-fast]

Prints a per-domain summary and exits non-zero if any link is dead.
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)  # so the default sqlite:///./decor.sqlite3 resolves correctly

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.services.link_checker import check_url  # noqa: E402


def main() -> int:
    fail_fast = "--fail-fast" in sys.argv
    db = SessionLocal()
    try:
        products = list(db.scalars(select(Product).where(Product.seller_link != "")))
        print(f"checking {len(products)} product links…")
        unique_urls = sorted({p.seller_link for p in products})
        results: dict[str, bool] = {}
        for url in unique_urls:
            ok = check_url(url)
            results[url] = ok
            print(f"  [{'OK ' if ok else 'DEAD'}] {url}")
            if not ok and fail_fast:
                return 1

        dead = 0
        for p in products:
            ok = results[p.seller_link]
            p.seller_link_ok = ok
            if not ok:
                dead += 1
        db.commit()

        domains = Counter(u.split("/")[2] for u in unique_urls)
        print(f"\ndomains: {dict(domains)}")
        print(f"result : {len(products) - dead}/{len(products)} links valid")
        return 1 if dead else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
