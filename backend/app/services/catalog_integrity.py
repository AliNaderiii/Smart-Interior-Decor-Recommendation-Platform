"""Catalog-integrity service — applies ``ai.catalog_integrity`` to ORM rows.

The policy module is pure; this module knows about the database: it looks up
which other products share an image, decides the enforcement mode from
``settings`` (strict in production), and writes the verdict onto the row
(``integrity_ok``, ``integrity_reasons``, ``integrity_checked_at``).

Enforcement points that call it:

* ``POST /products``, ``POST /products/upload``, ``PATCH /products/{id}`` —
  every write re-evaluates the row;
* ``POST /products/{id}/verify`` — refuses (409) to verify a failing row
  unless ``force=true`` (audited, stamped ``admin_override``);
* ``scripts/backfill_integrity.py`` — evaluates the whole table;
* ``scripts/audit_catalog.py`` — CI gate, read-only.

The recommender and visual search do not call it; they only read the column.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai import catalog_integrity as policy
from app.core.config import settings
from app.models.base import utcnow
from app.models.product import Product

logger = logging.getLogger(__name__)


def strict_mode() -> bool:
    """Production enforces the sellability tier; dev/test/CI only the truth tier."""
    return settings.is_production


def image_index(db: Session, products: Iterable[Product] | None = None) -> dict[str, set[str]]:
    """Map :func:`policy.image_key` -> product ids for the whole table.

    One query; the table is small (hundreds to low thousands of rows). When
    ``products`` is given, unsaved rows in it are folded in so a batch import
    detects duplicates inside itself too.
    """
    index: dict[str, set[str]] = defaultdict(set)
    rows = db.execute(select(Product.id, Product.image_url, Product.image_phash)).all()
    for pid, url, phash in rows:
        key = policy.image_key(url, phash)
        if key:
            index[key].add(pid)
    for p in products or ():
        key = policy.image_key(p.image_url, p.image_phash)
        if key and p.id:
            index[key].add(p.id)
    return index


def evaluate(
    product: Product,
    *,
    db: Session | None = None,
    strict: bool | None = None,
    known_images: dict[str, set[str]] | None = None,
    now: datetime | None = None,
    observed: Iterable[str] = (),
) -> dict:
    """Compute the decision for ``product`` (no writes)."""
    if known_images is None and db is not None:
        known_images = image_index(db, [product])
    return policy.integrity_decision(
        product,
        strict=strict_mode() if strict is None else strict,
        known_images=known_images,
        now=now,
        observed=observed,
    )


def stamp(product: Product, decision: dict, *, keep_override: bool = False) -> dict:
    """Write the decision onto the row. Returns the decision for chaining.

    ``keep_override`` preserves an existing ``admin_override`` marker (a
    forced verification survives re-evaluation of unrelated fields).
    """
    reasons = list(decision["reasons"])
    previous = product.integrity_reasons or []
    if keep_override and policy.ADMIN_OVERRIDE in previous and reasons:
        reasons.append(policy.ADMIN_OVERRIDE)
        product.integrity_ok = True
    else:
        product.integrity_ok = decision["ok"]
    product.integrity_reasons = reasons
    product.integrity_checked_at = utcnow()
    return decision


def refresh(
    product: Product,
    db: Session,
    *,
    strict: bool | None = None,
    known_images: dict[str, set[str]] | None = None,
    keep_override: bool = True,
) -> dict:
    """Evaluate + stamp in one call (the write paths use this)."""
    decision = evaluate(product, db=db, strict=strict, known_images=known_images)
    return stamp(product, decision, keep_override=keep_override)


def force_override(product: Product, decision: dict) -> None:
    """Admin verified a failing row on purpose: eligible, but the reasons and
    the override marker stay visible on the row and in the API."""
    product.integrity_ok = True
    product.integrity_reasons = [*decision["reasons"], policy.ADMIN_OVERRIDE]
    product.integrity_checked_at = utcnow()


def summary(db: Session) -> dict:
    """Counts for ``GET /admin/stats`` and the audit script."""
    rows = db.execute(
        select(Product.category, Product.is_verified, Product.integrity_ok, Product.integrity_reasons)
    ).all()
    per_category: dict[str, dict[str, int]] = defaultdict(lambda: {"eligible": 0, "excluded": 0, "unchecked": 0})
    reason_counts: dict[str, int] = defaultdict(int)
    for category, verified, ok, reasons in rows:
        if not verified:
            continue
        bucket = "unchecked" if ok is None else ("eligible" if ok else "excluded")
        per_category[category][bucket] += 1
        for code in reasons or []:
            reason_counts[code] += 1
    return {
        "policy_version": policy.INTEGRITY_POLICY_VERSION,
        "strict": strict_mode(),
        "by_category": dict(per_category),
        "reason_counts": dict(sorted(reason_counts.items())),
    }
