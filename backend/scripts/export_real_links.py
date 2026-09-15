"""Export the live catalog's REAL rows as a seller-feed file for CI link-liveness.

The CI job ``link-liveness`` proves the ad's acceptance criterion «every
shopping-list link is valid» — which only means something over the links a
shopper is actually shown. This script asks the deployed API (as an
administrator, read-only) for every verified, non-synthetic row and writes
them in the importer's own file contract (``seed_data/feed_template.csv``
columns, JSON ``{"items": [...]}``), so CI can load them through the same
write path as production and probe exactly those seller links.

    # from backend/, venv active — password asked interactively, never a flag
    python scripts/export_real_links.py --api https://smartdecor-backend.onrender.com/api/v1 \\
        --out seed_data/products_real_links.json

    # then: review the diff, commit, push — CI switches to "real" mode by itself

What is (not) in the file: title, category, price, image URL, seller link,
dimensions, tags, price_checked_at, the source product id — the public
product card, nothing else. No user data, no tokens, no internal ids
(``source_product_id`` is the seller's id, e.g. the Basalam product number).

Exit codes: 0 written, 1 nothing to export (no real verified rows yet —
import first), 2 bad usage / authentication.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai import catalog_integrity as policy  # noqa: E402

EXIT_OK, EXIT_EMPTY, EXIT_USAGE = 0, 1, 2


def _login(client: httpx.Client, email: str, password: str) -> str:
    resp = client.post("/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        raise SystemExit(f"login failed: HTTP {resp.status_code} {resp.text[:200]}")
    return resp.json()["data"]["access_token"]


def fetch_products(client: httpx.Client, page_size: int = 100) -> list[dict]:
    """Walk ``GET /products`` (admin) page by page."""
    out: list[dict] = []
    page = 1
    while True:
        resp = client.get("/products", params={"page": page, "page_size": page_size, "is_verified": "true"})
        if resp.status_code != 200:
            raise SystemExit(f"GET /products failed: HTTP {resp.status_code} {resp.text[:200]}")
        data = resp.json()["data"]
        items = data.get("items") or data.get("products") or []
        out.extend(items)
        total = int(data.get("total") or 0)
        if not items or len(out) >= total:
            return out
        page += 1


def to_feed_rows(products: list[dict]) -> list[dict]:
    """Verified, non-synthetic rows → importer file rows (template columns)."""
    rows: list[dict] = []
    for p in products:
        if not p.get("is_verified") or policy.is_synthetic(p) or not p.get("seller_link"):
            continue
        spid = p.get("source_product_id") or p.get("id")
        rows.append({
            "source_product_id": str(spid),
            "title_fa": p.get("title_fa") or p.get("title") or "",
            "title_en": p.get("title") or "",
            "category": p.get("category"),
            "price_toman": int(p.get("price_toman") or 0),
            "price_checked_at": p.get("price_checked_at") or datetime.now(timezone.utc).isoformat(),
            "image_url": p.get("image_url") or "",
            "seller_link": p.get("seller_link"),
            "width_cm": int(p.get("width_cm") or 0),
            "depth_cm": int(p.get("depth_cm") or 0),
            "height_cm": int(p.get("height_cm") or 0),
            "colors": "|".join(p.get("colors") or []),
            "styles": "|".join(p.get("styles") or []),
            "materials": "|".join(p.get("materials") or []),
            "patterns": "|".join(p.get("patterns") or []),
            "description": (p.get("description") or "")[:500],
            "available": "true",
            "seller_name": (p.get("source") or "").replace("feed:", ""),
            "_origin_source": p.get("source"),
        })
    rows.sort(key=lambda r: (r["category"], r["source_product_id"]))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", required=True, help="e.g. https://smartdecor-backend.onrender.com/api/v1")
    parser.add_argument("--out", type=Path, default=Path("seed_data/products_real_links.json"))
    parser.add_argument("--admin-email", default="admin@smartdecor.dev")
    parser.add_argument("--token", default=None, help="existing access token (automation)")
    parser.add_argument("--timeout", type=float, default=120.0, help="Render cold start needs ~60 s")
    args = parser.parse_args(argv)

    with httpx.Client(base_url=args.api.rstrip("/"), timeout=args.timeout) as client:
        token = args.token or _login(client, args.admin_email, getpass.getpass("admin password: "))
        client.headers["Authorization"] = f"Bearer {token}"
        products = fetch_products(client)

    rows = to_feed_rows(products)
    by_source: dict[str, int] = {}
    for r in rows:
        by_source[r["_origin_source"] or "?"] = by_source.get(r["_origin_source"] or "?", 0) + 1
    print(f"verified rows fetched: {len(products)}; real rows with a seller link: {len(rows)} {by_source}")
    if not rows:
        print("nothing to export yet — import real rows first (scripts/import_catalog.py).", file=sys.stderr)
        return EXIT_EMPTY
    for r in rows:
        r.pop("_origin_source", None)
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "api": args.api,
        "note": "CI link-liveness fixture — verified, non-synthetic rows of the live catalog in the "
                "importer file contract. Regenerate with scripts/export_real_links.py after each import.",
        "items": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"written: {args.out} ({len(rows)} rows)")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
