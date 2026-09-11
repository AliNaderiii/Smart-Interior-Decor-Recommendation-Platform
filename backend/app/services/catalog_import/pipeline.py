"""FeedRow → Product: the one write path for imported catalog rows.

Per row, in order — and every step can only *reject* or *flag*, never invent:

1. :func:`normalize_row` — structure (price, URL, category mapping);
2. image acquisition (:mod:`.images`) — SSRF-guarded fetch, upload-grade
   validation, perceptual hash, re-hosting on the platform's storage;
3. vision check — the configured :class:`ai.feature_extractor.FeatureExtractor`
   looks at the *bytes* and reports ``detected_category`` (+ style/material/
   colour tags for the blanks the seller left). In production that is the
   real provider or a refused boot; the mock never reaches a sold deployment
   (Stage 04 guard);
4. upsert by ``(source, source_product_id)`` — re-running an import updates
   price/availability/link instead of duplicating rows;
5. embedding (real backend in production — ``hash`` is refused there);
6. ADR-016 integrity stamp (:func:`app.services.catalog_integrity.refresh`)
   with an in-batch duplicate-image index;
7. ``is_verified`` — stays ``False`` (admin review queue) unless the operator
   passed ``verify=True`` **and** the row is clean **and** the vision check
   agreed with the row's category. Verification is never implied. The only
   softening is explicit and audited: ``tolerate={"ambiguous_style"}``
   (P4-ب·2e) verifies a row whose *sole* review flag is the style hedge, and
   the flag stays stored on the row.

Two decisions sit between steps 1 and 4 (P4-ب·2e, 2026-09-11):

* an adapter may mark a row ``off_scope`` (a park lamp, a kids' chair, a
  book set the search engine returned) — it is skipped *before* the image
  is downloaded or the vision provider is paid, and counted in the report;
* an adapter may carry two ``category_candidates`` (the seller's label and
  the search term disagree — an armchair filed under «مبل»). The picture
  decides: when ``detected_category`` is one of the two, the row is filed
  there (``category_resolved_by_image`` in the warnings and in
  ``extraction_raw.import``); when it is neither, the row is an
  ``image_category_mismatch`` exactly as before.

A dry run performs 1–3 and 6 (evaluate only), writes nothing — not even an
image — and reports exactly what a real run would do.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai import catalog_integrity as policy
from ai import taxonomy as tax
from ai.embedding_service import get_embedding, product_to_text
from ai.extraction_review import TOLERABLE_REVIEW_REASONS
from app.core.log_redaction import redact
from app.models.product import Product
from app.services import catalog_integrity as integrity
from app.services.catalog_import.contract import FeedRow, RowRejected, normalize_row
from app.services.catalog_import.images import AcquiredImage, ImageUnavailable, acquire, persist

logger = logging.getLogger(__name__)

IMPORT_POLICY_VERSION = "catalog_import/2026-09-11.1"

ImageFetcher = Callable[[str], AcquiredImage]
LinkChecker = Callable[[str], Any]  # returns app.services.link_checker.LinkCheckResult


@dataclass(frozen=True)
class ImportOptions:
    #: Evaluate everything, write nothing (default — same posture as purge_accounts).
    dry_run: bool = True
    #: Run the vision provider on the image bytes (``detected_category`` etc.).
    vision: bool = True
    #: Mark clean rows verified. Requires ``vision`` — a row cannot be
    #: auto-verified without the image check that makes the gate meaningful.
    verify: bool = False
    #: Probe ``seller_link`` (HEAD/GET, SSRF-guarded) and store the verdict.
    check_links: bool = True
    #: Stop after this many *accepted* rows (operator smoke tests).
    limit: int | None = None
    #: Skip rows the feed marks unavailable (a product you cannot buy is not a
    #: recommendation). Existing rows that became unavailable are un-verified.
    skip_unavailable: bool = True
    #: Seconds for each image download.
    image_timeout: float = 30.0
    #: ``rehost`` copies the validated bytes to the platform's storage and
    #: serves them from there; ``link`` keeps the seller's URL as
    #: ``image_url`` (bytes are still fetched for the fingerprint and the
    #: vision check). ``None`` = ``rehost`` when S3 is configured, else
    #: ``link`` — local storage on a PaaS is wiped on every deploy.
    image_mode: str | None = None
    #: Re-download every picture even when the feed URL is unchanged (new
    #: vision provider, changed thresholds …). Default: reuse the stored
    #: fingerprint and verdict.
    refresh_images: bool = False
    #: Review reasons the operator accepts at verification time (``--tolerate``).
    #: Only :data:`ai.extraction_review.TOLERABLE_REVIEW_REASONS` are allowed;
    #: a row is verified when *every* reason it carries is tolerated, and the
    #: reasons stay on the row (``extraction_raw.review_reasons`` +
    #: ``extraction_raw.import.tolerated``). Default: tolerate nothing.
    tolerate: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.verify and not self.vision:
            raise ValueError("verify=True requires vision=True (no auto-verification without the image check)")
        if self.image_mode not in (None, "rehost", "link"):
            raise ValueError("image_mode must be 'rehost' or 'link'")
        tolerate = frozenset(str(r) for r in (self.tolerate or ()))
        object.__setattr__(self, "tolerate", tolerate)
        unknown = sorted(tolerate - TOLERABLE_REVIEW_REASONS)
        if unknown:
            raise ValueError(
                f"tolerate={unknown} is not allowed; only {sorted(TOLERABLE_REVIEW_REASONS)} may be tolerated "
                "(every other review reason means a feature is missing, invented or from a failed provider)"
            )
        if tolerate and not self.verify:
            raise ValueError("tolerate=... only affects verify=True (nothing is verified without --verify)")

    def resolved_image_mode(self) -> str:
        if self.image_mode:
            return self.image_mode
        from app.core.config import settings

        return "rehost" if settings.STORAGE_BACKEND == "s3" else "link"


@dataclass
class RowResult:
    source_product_id: str
    action: str = "pending"  # created | updated | unchanged | rejected | skipped
    title_fa: str = ""
    category: str = ""
    product_id: str | None = None
    #: Rejection / skip codes (normaliser, image step) — stable identifiers.
    codes: list[str] = field(default_factory=list)
    #: ADR-016 verdict for accepted rows.
    integrity_ok: bool | None = None
    integrity_reasons: list[str] = field(default_factory=list)
    detected_category: str | None = None
    needs_review: bool | None = None
    #: Why the vision gate wants a human (``low_confidence``, ``missing_style``,
    #: ``provider_error`` …) — the operator reads these before deciding ``--yes``.
    review_reasons: list[str] = field(default_factory=list)
    #: Review reasons the operator tolerated (``ImportOptions.tolerate``) —
    #: non-empty only when the row was verified *despite* them.
    tolerated_reasons: list[str] = field(default_factory=list)
    verified: bool = False
    #: Every category the adapter's signals named (seller label, search term);
    #: two entries mean the picture had to decide.
    category_candidates: list[str] = field(default_factory=list)
    #: ``"image"`` when ``detected_category`` chose between two candidates.
    category_resolved_by: str | None = None
    #: The URL the product now serves its picture from (own storage or seller CDN).
    image_url: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class ImportReport:
    source: str
    dry_run: bool
    strict: bool
    started_at: str
    rows: list[RowResult] = field(default_factory=list)

    def count(self, action: str) -> int:
        return sum(1 for r in self.rows if r.action == action)

    @property
    def accepted(self) -> list[RowResult]:
        return [r for r in self.rows if r.action in ("created", "updated", "unchanged")]

    def summary(self) -> dict[str, Any]:
        reasons: Counter[str] = Counter()
        codes: Counter[str] = Counter()
        categories: Counter[str] = Counter()
        for r in self.rows:
            reasons.update(r.integrity_reasons)
            codes.update(r.codes)
            if r.action in ("created", "updated", "unchanged"):
                categories[r.category] += 1
        eligible = sum(1 for r in self.accepted if r.integrity_ok is not False)
        external_origins = sorted({
            _origin(r.image_url) for r in self.accepted if r.image_url.startswith(("http://", "https://"))
        } - {""})
        return {
            "source": self.source,
            "dry_run": self.dry_run,
            "strict": self.strict,
            "policy": IMPORT_POLICY_VERSION,
            "integrity_policy": policy.INTEGRITY_POLICY_VERSION,
            "started_at": self.started_at,
            "total": len(self.rows),
            "created": self.count("created"),
            "updated": self.count("updated"),
            "unchanged": self.count("unchanged"),
            "rejected": self.count("rejected"),
            "skipped": self.count("skipped"),
            "eligible": eligible,
            "excluded_by_integrity": sum(1 for r in self.accepted if r.integrity_ok is False),
            "verified": sum(1 for r in self.accepted if r.verified),
            #: Rows actually waiting for a human (flagged and not verified).
            "needs_review": sum(1 for r in self.accepted if r.needs_review and not r.verified),
            #: Rows verified although flagged, because every flag was tolerated.
            "tolerated": sum(1 for r in self.accepted if r.tolerated_reasons),
            "tolerated_reasons": dict(Counter(
                reason for r in self.accepted for reason in r.tolerated_reasons
            ).most_common()),
            "category_mismatch": sum(
                1 for r in self.accepted if "image_category_mismatch" in r.integrity_reasons
            ),
            "category_resolved_by_image": sum(1 for r in self.accepted if r.category_resolved_by == "image"),
            "off_scope": codes["off_scope"],
            "review_reasons": dict(Counter(
                reason for r in self.accepted if r.needs_review and not r.verified for reason in r.review_reasons
            ).most_common()),
            "by_category": dict(sorted(categories.items())),
            "integrity_reasons": dict(reasons.most_common()),
            "rejection_codes": dict(codes.most_common()),
            #: Third-party image origins the browser will load (image_mode=link):
            #: each must be listed in IMAGE_EXTRA_ORIGINS or the CSP blocks the picture.
            "external_image_origins": external_origins,
        }

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary(), "rows": [asdict(r) for r in self.rows]}


# ------------------------------------------------------------------- helpers

def _record(report: ImportReport, result: RowResult, on_row: Callable[[RowResult], None] | None) -> None:
    report.rows.append(result)
    if on_row is not None:
        try:
            on_row(result)
        except Exception as exc:  # a progress printer must never abort an import
            logger.debug("on_row callback failed: %s", exc)


def _origin(url: str) -> str:
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


def _existing_by_source(db: Session, source: str) -> dict[str, Product]:
    rows = db.scalars(select(Product).where(Product.source == source)).all()
    return {p.source_product_id: p for p in rows if p.source_product_id}


def _previous_import(product: Product | None) -> Mapping[str, Any]:
    raw = (product.extraction_raw or {}) if product is not None else {}
    meta = raw.get("import") if isinstance(raw, Mapping) else None
    return meta if isinstance(meta, Mapping) else {}


def _image_unchanged(product: Product | None, row: FeedRow) -> bool:
    """True when the row's picture is the one we already fetched for this product."""
    if product is None or not product.image_phash or not product.image_url:
        return False
    return _previous_import(product).get("image_url") == row.image_url


def _candidates(row: FeedRow) -> list[str]:
    """Taxonomy categories the adapter's signals named, filed category first."""
    raw = row.raw.get("category_candidates")
    known = set(tax.categories())
    out = [row.category] if row.category in known else []
    if isinstance(raw, (list, tuple)):
        out.extend(str(c) for c in raw if isinstance(c, str) and c in known and str(c) not in out)
    return out


def _category_source(row: FeedRow, category: str, resolved_by: str | None) -> str:
    """Provenance of the stored category: ``image`` (arbitrated), ``seller``
    (the seller's own label), ``query`` (the search term's target) or ``feed``
    (a file feed's column)."""
    if resolved_by:
        return resolved_by
    if "seller_category" in row.raw or "target_category" in row.raw:
        if row.raw.get("seller_category") == category:
            return "seller"
        if row.raw.get("target_category") == category:
            return "query"
    return "feed"


def _merge_tags(seller: list[str], vision: Any) -> list[str]:
    """Seller-declared tags win; the vision model only fills blanks."""
    if seller:
        return list(seller)
    return [str(v) for v in vision] if isinstance(vision, (list, tuple)) else []


def _embed(product: Product) -> None:
    product.style_embedding = get_embedding(product_to_text(
        product.title, product.styles or [], product.colors or [],
        product.materials or [], product.description or "", product.patterns or [],
    ))


def _stamp_link(product: Product, result: Any, now: datetime) -> None:
    product.seller_link_ok = bool(getattr(result, "ok", False))
    product.link_status = getattr(result, "classification", None)
    product.link_checked_at = now


# ------------------------------------------------------------------ the loop

def import_rows(
    db: Session,
    raw_rows: Iterable[Mapping[str, Any]],
    *,
    source: str,
    options: ImportOptions | None = None,
    now: datetime | None = None,
    extractor: Any | None = None,
    fetch_image: ImageFetcher | None = None,
    check_link: LinkChecker | None = None,
    category_aliases: Mapping[str, str] | None = None,
    default_category: str | None = None,
    allow_local_images: bool = False,
    on_row: Callable[[RowResult], None] | None = None,
) -> ImportReport:
    """Import ``raw_rows`` (adapter output) under ``source``. Returns the report.

    Commits once at the end (or rolls back on ``dry_run``). ``extractor``,
    ``fetch_image`` and ``check_link`` are injectable for tests; the defaults
    are the production components. ``on_row`` is called with each finished
    :class:`RowResult` (the CLI prints progress from it; a callback failure
    never aborts the import).
    """
    opts = options or ImportOptions()
    moment = now or datetime.now(timezone.utc)
    report = ImportReport(
        source=source, dry_run=opts.dry_run, strict=integrity.strict_mode(),
        started_at=moment.isoformat(),
    )
    image_mode = opts.resolved_image_mode()
    if allow_local_images and image_mode != "rehost":
        raise ValueError("local image paths can only be imported with image_mode='rehost'")
    persist_images = image_mode == "rehost" and not opts.dry_run
    if fetch_image is None:
        def fetch_image(url: str, _timeout: float = opts.image_timeout) -> AcquiredImage:
            return acquire(url, timeout=_timeout, store=False)
    if check_link is None and opts.check_links:
        from app.services.link_checker import check_url_detailed

        check_link = check_url_detailed
    if extractor is None and opts.vision:
        from ai.feature_extractor import FeatureExtractor

        extractor = FeatureExtractor()

    existing = _existing_by_source(db, source)
    known_images: dict[str, set[str]] = defaultdict(set, integrity.image_index(db))
    accepted = 0

    for raw in raw_rows:
        if opts.limit is not None and accepted >= opts.limit:
            break
        spid = str(raw.get("source_product_id") or raw.get("id") or "")
        try:
            row = normalize_row(
                raw, source=source, now=moment, allow_local_images=allow_local_images,
                category_aliases=category_aliases, default_category=default_category,
            )
        except RowRejected as exc:
            # ``details`` say what was seen (missing photo, rial price out of
            # band …) so the report explains a rejection without the raw dump.
            _record(report, RowResult(source_product_id=spid, action="rejected", codes=exc.codes,
                                      title_fa=exc.title_fa, warnings=exc.details), on_row)
            continue

        result = RowResult(source_product_id=row.source_product_id, title_fa=row.title_fa,
                           category=row.category, warnings=list(row.warnings))
        result.category_candidates = _candidates(row)
        product = existing.get(row.source_product_id)

        off_scope = str(row.raw.get("off_scope") or "").strip()
        if off_scope:
            # The adapter recognised something that is not living-room decor
            # (a park lamp, a kids' chair, a book set). Nothing is downloaded,
            # nothing is inferred, nothing is written; an existing row is left
            # for the admin queue rather than silently changed.
            result.action = "skipped"
            result.codes = ["off_scope"]
            result.warnings.append(off_scope)
            if product is not None:
                result.product_id = product.id
                result.warnings.append(f"already in the catalog as product {product.id}; review it in /admin/products")
            _record(report, result, on_row)
            continue

        if not row.available and opts.skip_unavailable:
            result.action = "skipped"
            result.codes = ["unavailable"]
            if product is not None and product.is_verified:
                # It used to be recommendable; it no longer can be bought.
                product.is_verified = False
                meta = dict(_previous_import(product))
                meta["unavailable_at"] = moment.isoformat()
                product.extraction_raw = {**(product.extraction_raw or {}), "import": meta}
                result.product_id = product.id
            _record(report, result, on_row)
            continue

        # ---- image -------------------------------------------------------
        image: AcquiredImage | None = None
        if not opts.refresh_images and _image_unchanged(product, row):
            hosted_url, phash = product.image_url, product.image_phash  # type: ignore[union-attr]
        else:
            try:
                image = fetch_image(row.image_url)
            except ImageUnavailable as exc:
                result.action = "rejected"
                result.codes = [exc.code]
                result.warnings.append(exc.detail[:200])
                _record(report, result, on_row)
                continue
            phash = image.phash
            if product is None and phash:
                twins = known_images.get(f"phash:{phash.lower()}") or set()
                if twins:
                    # Same picture already in the catalog (Basalam resellers
                    # share manufacturer photos). Do not create a second row;
                    # the gate would only exclude it later. Nothing was stored.
                    result.action = "skipped"
                    result.codes = ["duplicate_image"]
                    result.warnings.append(f"same image as product {sorted(twins)[0]}")
                    _record(report, result, on_row)
                    continue
            if persist_images:
                persist(image)
            hosted_url = image.hosted_url if (image_mode == "rehost" and image.hosted_url) else row.image_url

        # ---- vision ------------------------------------------------------
        extraction: dict[str, Any] = {}
        if opts.vision and extractor is not None:
            if image is None:
                # Unchanged picture: keep the previous verdict instead of paying
                # for the same inference twice.
                previous = product.extraction_raw if product is not None else {}
                extraction = {k: v for k, v in (previous or {}).items() if k != "import"}
            else:
                hint = row.image_url.rsplit("/", 1)[-1] or "feed.jpg"
                try:
                    extraction = extractor.extract_bytes(
                        image.data, mime=image.content_type, image_hint=hint, prompt_kind="product",
                    )
                except Exception as exc:  # provider outage: flag, never fabricate
                    logger.warning("vision extraction failed for %s: %s", row.source_product_id, exc)
                    extraction = {"provider_error": redact(f"{type(exc).__name__}: {exc}"[:200]),
                                  "needs_review": True, "review_reasons": ["provider_error"]}
        detected = extraction.get("detected_category")
        result.detected_category = detected if isinstance(detected, str) else None
        result.needs_review = bool(extraction.get("needs_review")) if extraction else None
        result.review_reasons = [str(r) for r in (extraction.get("review_reasons") or []) if r]

        # ---- category: the picture arbitrates between two candidates -----
        category = row.category
        if (
            len(result.category_candidates) > 1
            and result.detected_category in result.category_candidates
            and result.detected_category != category
        ):
            category = result.detected_category
            result.category_resolved_by = "image"
            result.warnings.append(f"category_resolved_by_image:{row.category}->{category}")
        result.category = category

        # ---- upsert ------------------------------------------------------
        created = product is None
        if created:
            product = Product(source=source, source_product_id=row.source_product_id, is_verified=False)
            db.add(product)
        assert product is not None
        before = _snapshot(product)

        product.title = row.title_en or row.title_fa
        product.title_fa = row.title_fa
        product.category = category
        product.room_type = row.room_type
        product.price_toman = row.price_toman
        product.price_checked_at = row.price_checked_at
        product.image_url = hosted_url
        product.image_phash = phash or None
        product.seller_link = row.seller_link
        product.width_cm, product.depth_cm, product.height_cm = row.width_cm, row.depth_cm, row.height_cm
        product.colors = _merge_tags(row.colors, extraction.get("colors"))
        product.styles = _merge_tags(row.styles, extraction.get("style"))
        product.materials = _merge_tags(row.materials, extraction.get("material"))
        product.patterns = _merge_tags(row.patterns, extraction.get("patterns"))
        product.description = row.description or str(extraction.get("description_for_embedding") or "")[:2000]
        product.extraction_confidence = float(extraction.get("confidence") or 0.0)
        product.extraction_raw = {
            **{k: v for k, v in extraction.items() if k != "import"},
            "detected_category": result.detected_category,
            "import": {
                "policy": IMPORT_POLICY_VERSION,
                "source": source,
                "source_product_id": row.source_product_id,
                "image_url": row.image_url,
                "seller_name": row.seller_name,
                "feed_category": str(row.raw.get("feed_category") or row.raw.get("category") or ""),
                "category_candidates": list(result.category_candidates),
                "category_resolved_by": _category_source(row, category, result.category_resolved_by),
                "image_mode": image_mode,
                "imported_at": moment.isoformat(),
                "warnings": row.warnings,
            },
        }
        if created or _snapshot(product) != before:
            _embed(product)

        if opts.check_links and check_link is not None and row.seller_link:
            try:
                _stamp_link(product, check_link(row.seller_link), moment)
            except Exception as exc:  # never let a probe abort the import
                logger.warning("link check failed for %s: %s", row.source_product_id, exc)

        db.flush()  # id assigned → the duplicate index can exclude self
        key = policy.image_key(product.image_url, product.image_phash)
        if key:
            known_images[key].add(product.id)
        decision = integrity.refresh(product, db, known_images=known_images, keep_override=True)
        result.integrity_ok = product.integrity_ok
        result.integrity_reasons = list(product.integrity_reasons or [])

        if opts.verify:
            # Every review reason must be one the operator explicitly tolerates
            # (and a flag without a reason is never tolerated).
            blocking = [r for r in result.review_reasons if r not in opts.tolerate]
            flagged = bool(result.needs_review)
            review_clear = not flagged or (bool(result.review_reasons) and not blocking)
            clean = decision["ok"] and review_clear and result.detected_category == category
            if clean:
                product.is_verified = True
                if flagged:
                    result.tolerated_reasons = list(result.review_reasons)
                    meta = dict(product.extraction_raw.get("import") or {})
                    meta["tolerated"] = list(result.review_reasons)
                    product.extraction_raw = {**product.extraction_raw, "import": meta}
        result.verified = bool(product.is_verified)
        result.image_url = product.image_url or ""
        result.product_id = product.id
        result.action = "created" if created else ("updated" if _snapshot(product) != before else "unchanged")
        existing[row.source_product_id] = product
        _record(report, result, on_row)
        accepted += 1

    if opts.dry_run:
        db.rollback()
    else:
        _audit(db, report)
        db.commit()
        _flush_recommendation_cache()
    return report


_SNAPSHOT_FIELDS = (
    "title", "title_fa", "category", "room_type", "price_toman", "image_url", "image_phash",
    "seller_link", "width_cm", "depth_cm", "height_cm", "colors", "styles", "materials",
    "patterns", "description",
)


def _snapshot(product: Product) -> tuple:
    return tuple(
        tuple(v) if isinstance(v, list) else v
        for v in (getattr(product, f, None) for f in _SNAPSHOT_FIELDS)
    )


def _audit(db: Session, report: ImportReport) -> None:
    try:
        from app.models import audit_log as actions
        from app.services import audit

        s = report.summary()
        audit.record(
            db, actions.ACTION_CATALOG_IMPORT, commit=False,
            detail=(
                f"source={s['source']} created={s['created']} updated={s['updated']} "
                f"unchanged={s['unchanged']} rejected={s['rejected']} skipped={s['skipped']} "
                f"excluded={s['excluded_by_integrity']} verified={s['verified']} tolerated={s['tolerated']} "
                f"off_scope={s['off_scope']} strict={s['strict']}"
            ),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("catalog import audit row not written: %s", exc)


def _flush_recommendation_cache() -> int:
    """Cached /recommend payloads may reference prices/rows that just changed."""
    try:
        from app.core.redis_client import get_redis

        redis = get_redis()
        keys = list(redis.scan_iter("rec:*"))
        if keys:
            redis.delete(*keys)
        return len(keys)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("recommendation cache not flushed after import: %s", exc)
        return 0
