"""Seller-link validation — background task sets Product.seller_link_ok."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "SmartDecorLinkChecker/1.0"}


def check_url(url: str, timeout: float = 10.0) -> bool:
    """Return True if the URL answers 2xx/3xx to HEAD (GET fallback)."""
    if not url:
        return False
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=_HEADERS) as client:
            resp = client.head(url)
            if resp.status_code in (405, 403, 501):
                resp = client.get(url)
            return 200 <= resp.status_code < 400
    except httpx.HTTPError as exc:
        logger.warning("link check failed for %s: %s", url, exc)
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
