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
import time
from dataclasses import dataclass, field

import httpx

from app.core.url_safety import UnsafeUrl, validate_public_url

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "SmartDecorLinkChecker/1.0"}
#: Redirect chains are followed manually so every hop can be re-validated.
_MAX_REDIRECTS = 5


@dataclass
class LinkCheckResult:
    """Detailed outcome of one seller-link probe (Stage 2, T-2.5).

    ``classification`` is the operator-facing verdict:
      * ``ok``        — direct 2xx;
      * ``redirect``  — 2xx/3xx reached through 1+ validated redirects;
      * ``blocked``   — the host answered but refused the probe
                        (403/429 after the GET fallback: bot wall, not a dead
                        product page — needs a human/egress-host re-check);
      * ``dead``      — 4xx/5xx or a broken redirect chain;
      * ``unsafe``    — URL failed SSRF validation (never fetched);
      * ``error``     — network-level failure (DNS/TLS/timeout), with detail.
    """

    url: str
    ok: bool
    classification: str
    http_status: int | None = None
    latency_ms: float | None = None
    redirect_chain: list[str] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "ok": self.ok,
            "classification": self.classification,
            "http_status": self.http_status,
            "latency_ms": self.latency_ms,
            "redirect_chain": self.redirect_chain,
            "error": self.error,
        }


def check_url_detailed(url: str, timeout: float = 10.0) -> LinkCheckResult:
    """Probe ``url`` and return the full evidence record.

    Same protocol as the original ``check_url`` (HEAD with GET fallback on
    405/403/501, every redirect hop re-validated against SSRF, max 5 hops) —
    the boolean behaviour is unchanged; this variant additionally records
    status, latency, redirect chain and a classification.
    """
    if not url:
        return LinkCheckResult(url=url, ok=False, classification="dead",
                               error="empty url")
    try:
        target = validate_public_url(url, resolve=True, field="seller_link")
    except UnsafeUrl as exc:
        logger.warning("refusing to fetch unsafe seller link: %s", exc)
        return LinkCheckResult(url=url, ok=False, classification="unsafe",
                               error=str(exc))

    chain: list[str] = []
    started = time.perf_counter()

    def _elapsed() -> float:
        return round((time.perf_counter() - started) * 1000.0, 1)

    try:
        with httpx.Client(follow_redirects=False, timeout=timeout, headers=_HEADERS) as client:
            for _ in range(_MAX_REDIRECTS):
                resp = client.head(target)
                if resp.status_code in (405, 403, 501):
                    resp = client.get(target)
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location", "")
                    if not location:
                        return LinkCheckResult(
                            url=url, ok=False, classification="dead",
                            http_status=resp.status_code, latency_ms=_elapsed(),
                            redirect_chain=chain,
                            error="redirect without Location header")
                    nxt = str(httpx.URL(target).join(location))
                    try:
                        target = validate_public_url(
                            nxt, resolve=True, field="seller_link redirect"
                        )
                    except UnsafeUrl as exc:
                        logger.warning("blocked SSRF redirect: %s", exc)
                        return LinkCheckResult(
                            url=url, ok=False, classification="unsafe",
                            http_status=resp.status_code, latency_ms=_elapsed(),
                            redirect_chain=chain, error=f"unsafe redirect: {exc}")
                    chain.append(nxt)
                    continue
                ok = 200 <= resp.status_code < 400
                if ok:
                    cls = "redirect" if chain else "ok"
                elif resp.status_code in (403, 429):
                    cls = "blocked"
                else:
                    cls = "dead"
                return LinkCheckResult(
                    url=url, ok=ok, classification=cls,
                    http_status=resp.status_code, latency_ms=_elapsed(),
                    redirect_chain=chain)
        logger.warning("too many redirects while checking a seller link")
        return LinkCheckResult(url=url, ok=False, classification="dead",
                               latency_ms=_elapsed(), redirect_chain=chain,
                               error="too many redirects")
    except httpx.HTTPError as exc:
        logger.warning("link check failed: %s", exc)
        return LinkCheckResult(url=url, ok=False, classification="error",
                               latency_ms=_elapsed(), redirect_chain=chain,
                               error=f"{type(exc).__name__}: {exc}")


def check_url(url: str, timeout: float = 10.0) -> bool:
    """Return True if the URL answers 2xx/3xx to HEAD (GET fallback).

    Never follows a redirect into a private, loopback or link-local address.
    Thin boolean facade over :func:`check_url_detailed` (behaviour unchanged).
    """
    return check_url_detailed(url, timeout=timeout).ok



def check_product_link(product_id: str) -> None:
    """Background task: validate a product's seller link and persist result."""
    from app.db.session import SessionLocal
    from app.models.base import utcnow
    from app.models.product import Product

    db = SessionLocal()
    try:
        product = db.get(Product, product_id)
        if product and product.seller_link:
            res = check_url_detailed(product.seller_link)
            product.seller_link_ok = res.ok
            product.link_status = res.classification
            product.link_checked_at = utcnow()
            db.commit()
    finally:
        db.close()
