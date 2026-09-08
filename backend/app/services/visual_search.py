"""Visual search — "find furniture that looks like this photo" (ADR-013).

The user uploads a photo (an Instagram screenshot, a magazine page, a piece
they saw in a friend's flat) and gets the catalogue items that look most
like it. This is the "shop the look" feature every benchmarked competitor
sells (Houzz Visual Match, RoomStudioAI, Wayfair), built on infrastructure
the platform already has:

* every product carries a 512-d CLIP-space ``style_embedding`` (ADR-003);
* ``ai.embedding_service.get_embedding`` can embed an *image* in that same
  space when the CLIP backend is active — a photo and a product description
  then live in one vector space and cosine similarity is meaningful;
* on PostgreSQL the HNSW index answers the nearest-neighbour query.

Two retrieval modes, chosen by the active embedding backend and **reported
in the response** so the UI can say what it did:

``clip``
    The uploaded photo is embedded with CLIP's image tower and compared with
    the products' text-tower embeddings (cross-modal retrieval — the intended
    production path). The dominant palette is still extracted and folded in
    as a small colour prior, because CLIP is famously weak on exact colour.

``palette``
    Development / test / demo environments run the deterministic hash backend
    (``EMBEDDING_BACKEND=hash``), whose vectors carry **no** visual semantics.
    Embedding a photo there would be theatre. Instead the search degrades to
    something honest: k-means-free median-cut palette extraction from the
    pixels + the platform's own perceptual colour score (``color_score``,
    the same redmean metric used in the recommender) against each product's
    catalogued colours, plus a category filter. It is a real, useful search
    ("things in these colours") and it says so in ``meta.mode``.

Nothing here writes to the database, nothing is cached (photos are not
stored — see ADR-013 privacy note), and the endpoint is rate-limited like an
upload because it costs an embedding.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai import embedding_service
from app.models.product import Product
from app.services.recommender import (
    _product_payload,
    _session_is_postgres,
    color_score,
    cosine_similarity,
)

logger = logging.getLogger(__name__)

#: How many palette swatches to lift from the photo. Five is what a designer
#: writes on a mood board; more just adds noise from shadows and JPEG halos.
PALETTE_SIZE = 5
#: Photos are downscaled to this edge before quantisation — the palette does
#: not change beyond it, and it keeps the endpoint well under 50 ms on CPU.
_THUMB_EDGE = 128
#: Pure black/white pixels are usually mats, backgrounds and blown highlights,
#: not the object. They are demoted (not removed) when picking swatches.
_NEUTRAL_LUMA_LO = 22
_NEUTRAL_LUMA_HI = 238
#: Upper bound on candidates pulled from the database per search. A per-user
#: visual search is one query, not a scan of the whole catalogue.
CANDIDATE_LIMIT = 300
#: Blend for the CLIP path: cross-modal cosine carries the shape/style signal,
#: the palette score corrects CLIP's colour blindness.
CLIP_WEIGHT = 0.8
PALETTE_WEIGHT = 0.2


@dataclass(frozen=True)
class VisualQuery:
    """What was extracted from the photo, echoed back to the UI."""

    palette: list[str]
    mode: str  # "clip" | "palette"
    embedding: list[float] | None


def _luma(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def extract_palette(data: bytes, size: int = PALETTE_SIZE) -> list[str]:
    """Dominant colours of an image as upper-case ``#RRGGBB`` strings.

    Median-cut quantisation (Pillow, no numpy/sklearn) on a 128-px thumbnail,
    ordered by pixel share with near-black / near-white swatches demoted so a
    white wall does not become the "colour" of a green sofa. Deterministic:
    the same bytes always yield the same palette.
    """
    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGB")
        im.thumbnail((_THUMB_EDGE, _THUMB_EDGE))
        # More clusters than swatches so a large neutral background can be
        # demoted without starving the result of real object colours.
        quant = im.quantize(colors=max(size * 3, 8), method=Image.Quantize.MEDIANCUT)
        palette = quant.getpalette() or []
        counts = quant.getcolors(maxcolors=256) or []
    swatches: list[tuple[float, tuple[int, int, int]]] = []
    total = float(sum(c for c, _ in counts)) or 1.0
    for count, idx in counts:
        rgb = tuple(palette[idx * 3: idx * 3 + 3])
        if len(rgb) != 3:
            continue
        share = count / total
        luma = _luma(rgb)  # type: ignore[arg-type]
        if luma < _NEUTRAL_LUMA_LO or luma > _NEUTRAL_LUMA_HI:
            share *= 0.35
        swatches.append((share, rgb))  # type: ignore[arg-type]
    swatches.sort(key=lambda t: (-t[0], t[1]))
    out: list[str] = []
    for _, (r, g, b) in swatches:
        hex_ = f"#{r:02X}{g:02X}{b:02X}"
        if hex_ not in out:
            out.append(hex_)
        if len(out) >= size:
            break
    return out


def embed_query_image(data: bytes) -> VisualQuery:
    """Turn photo bytes into a :class:`VisualQuery` for the active backend."""
    palette = extract_palette(data)
    if embedding_service.get_backend() != "clip":
        return VisualQuery(palette=palette, mode="palette", embedding=None)
    model = embedding_service._load_clip()
    if model is None:  # pragma: no cover - get_backend() already checked
        return VisualQuery(palette=palette, mode="palette", embedding=None)
    with Image.open(io.BytesIO(data)) as im:
        vec = model.encode([im.convert("RGB")], normalize_embeddings=True)[0]
    return VisualQuery(palette=palette, mode="clip", embedding=[float(x) for x in vec])


def _candidates(
    db: Session, category: str | None, query: VisualQuery
) -> list[tuple[Product, float | None]]:
    """Verified living-room products (optionally one category) with, on the
    CLIP + PostgreSQL path, the HNSW-ordered cosine similarity attached."""
    where = [
        Product.room_type == "living_room",
        Product.is_verified.is_(True),
        Product.integrity_ok.isnot(False),  # ADR-016 catalog-integrity gate
    ]
    if category:
        where.append(Product.category == category)
    if query.embedding is not None and _session_is_postgres(db):
        dist = Product.style_embedding.cosine_distance(query.embedding)
        stmt = (
            select(Product, dist.label("dist"))
            .where(*where, Product.style_embedding.isnot(None))
            .order_by(dist, Product.id)
            .limit(CANDIDATE_LIMIT)
        )
        return [(row[0], max(0.0, min(1.0, 1.0 - row[1] / 2))) for row in db.execute(stmt)]
    stmt = select(Product).where(*where).order_by(Product.id).limit(CANDIDATE_LIMIT)
    return [(p, None) for p in db.scalars(stmt)]


def search(
    db: Session,
    data: bytes,
    *,
    category: str | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    """Rank catalogue products by visual similarity to ``data`` (image bytes).

    Returns ``{"items": [...], "meta": {...}}`` where each item is the usual
    product payload plus ``similarity`` (0-1) and ``palette_match`` (0-1), and
    ``meta`` echoes the extracted ``palette``, the retrieval ``mode`` and the
    ``category`` filter so the UI never has to guess what it is showing.
    """
    query = embed_query_image(data)
    rows: list[dict[str, Any]] = []
    for product, sim in _candidates(db, category, query):
        palette_match = color_score(query.palette, list(product.colors or []))
        if query.mode == "clip":
            if sim is None:
                emb = product.style_embedding
                raw = cosine_similarity(list(emb), query.embedding) if emb is not None else 0.0
                sim = max(0.0, min(1.0, (raw + 1) / 2))
            score = CLIP_WEIGHT * sim + PALETTE_WEIGHT * palette_match
        else:
            sim = None
            score = palette_match
        payload = _product_payload(product)
        payload["similarity"] = round(score, 4)
        payload["palette_match"] = round(palette_match, 4)
        if sim is not None:
            payload["clip_similarity"] = round(sim, 4)
        rows.append(payload)
    rows.sort(key=lambda r: (-r["similarity"], r["id"]))
    return {
        "items": rows[:limit],
        "meta": {
            "mode": query.mode,
            "palette": query.palette,
            "category": category,
            "candidates": len(rows),
            "embedding_backend": embedding_service.get_backend(),
        },
    }
