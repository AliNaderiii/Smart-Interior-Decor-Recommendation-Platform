"""Seller-link validation — background task sets Product.seller_link_ok.

Stage 03 (T-35): this is one of three server-side fetches of an
operator-supplied URL, and it followed redirects with no destination checks at
all. `http://169.254.169.254/latest/meta-data/…` would have been fetched
happily, as would `http://127.0.0.1:6379/`; a *public* URL that 302s to either
would also have worked, which is why the check has to be re-applied per hop
rather than once up front.

Validation also happens at the schema boundary
(`app.schemas.product`), but a stored row may predate that validator and DNS
answers change between validation and use (rebinding), so the outbound call
verifies again with `resolve=True`.
"""
from __future__ import annotations

import logging

import httpx

from app.core.url_safety import UnsafeUrl, validate_public_url

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "SmartDecorLinkChecker/1.0"}
#: Redirect chains are followed manually so every hop can be re-validated.
_MAX_REDIRECTS = 5


def check_url(url: str, timeout: float = 10.0) -> bool:
    """Return True if the URL answers 2xx/3xx to HEAD (GET fallback).

    Never follows a redirect into a private, loopback or link-local address.
    """
    if not url:
        return False
    try:
        target = validate_public_url(url, resolve=True, field="seller_link")
    except UnsafeUrl as exc:
        logger.warning("refusing to fetch unsafe seller link: %s", exc)
        return False

    try:
        with httpx.Client(follow_redirects=False, timeout=timeout, headers=_HEADERS) as client:
            for _ in range(_MAX_REDIRECTS):
                resp = client.head(target)
                if resp.status_code in (405, 403, 501):
                    resp = client.get(target)
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location", "")
                    if not location:
                        return False
                    nxt = str(httpx.URL(target).join(location))
                    try:
                        target = validate_public_url(
                            nxt, resolve=True, field="seller_link redirect"
                        )
                    except UnsafeUrl as exc:
                        logger.warning("blocked SSRF redirect: %s", exc)
                        return False
                    continue
                return 200 <= resp.status_code < 400
        logger.warning("too many redirects while checking a seller link")
        return False
    except httpx.HTTPError as exc:
        logger.warning("link check failed: %s", exc)
        return False


def check_product_link(product_id: str) -> None:
    """Background task: validate a product's seller link and persist result."""
    from app.db.session import SessionLocal
    from app.models.product import Product

    db = SessionLocal()
    try:
        product = db.get(Product, product_id)
        if product and product.seller_link:
            product.seller_link_ok = check_url(product.seller_link)
            db.commit()
    finally:
        db.close()
