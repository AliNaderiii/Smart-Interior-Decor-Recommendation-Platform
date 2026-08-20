"""Three-stage hybrid recommendation engine (ADR-005).

Stage A — Hard filter (SQL): room_type + category + budget window + is_verified.
Stage B — Semantic candidate retrieval: pgvector cosine distance
          ``style_embedding <=> :user_embedding LIMIT 100`` on Postgres;
          Python cosine fallback on SQLite (tests).
Stage C — Weighted scoring with full explainability:
          final = 0.30*style + 0.30*color + 0.20*budget + 0.15*material + 0.05*pattern

Results are cached in Redis under
``rec:{user_id}:{sha256(quiz-payload)}`` TTL 3600s — see ``quiz_cache_key``
for why the user id is part of the key.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Any

import orjson
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ai.embedding_service import cosine_similarity, get_embedding, quiz_to_text
from app.core.config import settings
from app.core.redis_client import get_redis
from app.models.product import CATEGORIES, Product

logger = logging.getLogger(__name__)

WEIGHTS = {
    "style": 0.30,
    "color": 0.30,
    "budget": 0.20,
    "material": 0.15,
    "pattern": 0.05,
}

CANDIDATE_LIMIT = 100
MIN_RESULTS, MAX_RESULTS = 3, 5


# ---------------------------------------------------------------------------
# Color math — hex -> RGB distance (approximate Delta-E via weighted RGB)
# ---------------------------------------------------------------------------
def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def color_distance(hex_a: str, hex_b: str) -> float:
    """Perceptually weighted RGB distance ('redmean'), normalized to 0..1."""
    try:
        r1, g1, b1 = _hex_to_rgb(hex_a)
        r2, g2, b2 = _hex_to_rgb(hex_b)
    except (ValueError, IndexError):
        return 1.0
    rmean = (r1 + r2) / 2
    dr, dg, db = r1 - r2, g1 - g2, b1 - b2
    dist = (
        ((2 + rmean / 256) * dr * dr)
        + 4 * dg * dg
        + ((2 + (255 - rmean) / 256) * db * db)
    ) ** 0.5
    return min(dist / 765.0, 1.0)


def color_score(user_palette: list[str], product_colors: list[str]) -> float:
    """Best-match average: for each user color, closest product color."""
    if not user_palette or not product_colors:
        return 0.5  # neutral when either side unknown
    total = 0.0
    for uc in user_palette:
        best = min(color_distance(uc, pc) for pc in product_colors)
        total += 1.0 - best
    return total / len(user_palette)


def budget_score(price: int, lo: int, hi: int) -> float:
    """1.0 at the midpoint of the budget window, linear falloff to edges."""
    if hi <= lo:
        return 1.0 if price == lo else 0.0
    mid = (lo + hi) / 2
    half = (hi - lo) / 2
    return max(0.0, 1.0 - abs(price - mid) / half) if half else 1.0


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.5
    return len(sa & sb) / len(sa | sb)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
def quiz_cache_key(quiz: dict[str, Any], user_id: str | None = None) -> str:
    """Stable Redis key for a quiz payload, scoped to the requesting user.

    V2 Phase 2 — the v1 key was ``rec:{sha256(quiz)}`` with no user component.
    That is too coarse in two ways:

    1. **Correctness/tenancy.** Two users who answer the quiz identically (very
       likely — the quiz is a small set of enumerated choices) shared one cache
       entry. Anything user-specific layered on top of the result (the Pro
       paywall masking in ``/recommend``, and per-user re-ranking planned for
       v2.1) would then leak across accounts. Scoping by user id makes the
       entry private by construction rather than relying on every caller to
       re-apply its own masking.
    2. **Invalidation.** A per-user prefix lets us drop one account's cached
       recommendations (e.g. after they upgrade to Pro) without flushing the
       whole ``rec:*`` namespace.

    ``user_id`` stays optional so internal/anonymous callers and the existing
    unit tests keep working with a shared key.
    """
    canonical = orjson.dumps(quiz, option=orjson.OPT_SORT_KEYS, default=str)
    digest = hashlib.sha256(canonical).hexdigest()
    return f"rec:{user_id}:{digest}" if user_id else f"rec:{digest}"


def _stage_a_hard_filter(
    db: Session, category: str, lo: int, hi: int
) -> list[Product]:
    """Stage A: SQL hard filter on category/budget/verification."""
    stmt = (
        select(Product)
        .where(
            Product.room_type == "living_room",
            Product.category == category,
            Product.is_verified.is_(True),
            Product.price_toman >= lo,
            Product.price_toman <= hi,
        )
    )
    return list(db.scalars(stmt))


def _stage_b_semantic(
    db: Session, candidates: list[Product], user_emb: list[float]
) -> list[tuple[Product, float]]:
    """Stage B: rank candidates by cosine similarity to the quiz embedding.

    On Postgres this would use ``ORDER BY style_embedding <=> :emb LIMIT 100``
    at the SQL level (see ``_stage_ab_postgres``); here we score the already
    hard-filtered set, which is exactly equivalent for per-category pools
    under the candidate limit.
    """
    scored = []
    for p in candidates:
        emb = p.style_embedding
        sim = cosine_similarity(list(emb), user_emb) if emb is not None else 0.0
        scored.append((p, max(0.0, min(1.0, (sim + 1) / 2))))  # map [-1,1] -> [0,1]
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:CANDIDATE_LIMIT]


def _stage_ab_postgres(
    db: Session, category: str, lo: int, hi: int, user_emb: list[float]
) -> list[tuple[Product, float]]:
    """Stages A+B fused in one pgvector query (production path).

    Recall note (V2 Phase 2): this is a post-filtered ANN search — the HNSW
    index orders by cosine distance while the WHERE clause discards anything
    outside the category/budget/verified window. With pgvector's default
    ``hnsw.ef_search = 40`` the index only visits ~40 nodes, so on a catalog
    of any real size most of them are filtered away and we silently return far
    fewer than ``CANDIDATE_LIMIT`` candidates to score (measured: 14/100 at
    20.7k rows). Raising ef_search for the duration of the transaction
    restores full recall while keeping the index scan cheaper than a seq scan.
    """
    db.execute(text(f"SET LOCAL hnsw.ef_search = {int(settings.HNSW_EF_SEARCH)}"))
    dist = Product.style_embedding.cosine_distance(user_emb)
    stmt = (
        select(Product, dist.label("dist"))
        .where(
            Product.room_type == "living_room",
            Product.category == category,
            Product.is_verified.is_(True),
            Product.price_toman >= lo,
            Product.price_toman <= hi,
            Product.style_embedding.isnot(None),
        )
        .order_by(dist)
        .limit(CANDIDATE_LIMIT)
    )
    rows = db.execute(stmt).all()
    return [(row[0], max(0.0, min(1.0, 1.0 - row[1] / 2))) for row in rows]


def calculate_score(product: Product, quiz: dict[str, Any], style_sim: float) -> dict[str, Any]:
    """Stage C weighted scoring with a full explainability breakdown."""
    c_score = color_score(quiz.get("color_palette", []), product.colors or [])
    b_score = budget_score(
        product.price_toman,
        quiz.get("budget_min_toman", 0),
        quiz.get("budget_max_toman", 10**9),
    )
    m_score = jaccard(quiz.get("materials", []), product.materials or [])
    p_score = jaccard(quiz.get("patterns", []), product.patterns or [])

    final = (
        WEIGHTS["style"] * style_sim
        + WEIGHTS["color"] * c_score
        + WEIGHTS["budget"] * b_score
        + WEIGHTS["material"] * m_score
        + WEIGHTS["pattern"] * p_score
    )

    matched_materials = sorted(set(quiz.get("materials", [])) & set(product.materials or []))
    return {
        "final_score": round(final, 4),
        "explanation": {
            "style_match": round(style_sim * 100),
            "color_match": round(c_score * 100),
            "budget_fit": round(b_score * 100),
            "material_match": round(m_score * 100),
            "pattern_match": round(p_score * 100),
            "matched_materials": matched_materials,
            "summary": (
                f"Style Match {round(style_sim * 100)}% | "
                f"Color Match {round(c_score * 100)}% | "
                f"Budget Fit {round(b_score * 100)}%"
                + (
                    f" | Material: {', '.join(matched_materials)} (matches your choice)"
                    if matched_materials
                    else ""
                )
            ),
        },
    }


def _product_payload(p: Product) -> dict[str, Any]:
    return {
        "id": p.id,
        "title": p.title,
        "title_fa": p.title_fa,
        "category": p.category,
        "price_toman": p.price_toman,
        "image_url": p.image_url,
        "seller_link": p.seller_link,
        "seller_link_ok": p.seller_link_ok,
        "colors": p.colors,
        "styles": p.styles,
        "materials": p.materials,
        "patterns": p.patterns,
        "width_cm": p.width_cm,
        "depth_cm": p.depth_cm,
        "height_cm": p.height_cm,
        "description": p.description,
    }


# ---------------------------------------------------------------------------
# Cache stampede protection (V2 Phase 2)
# ---------------------------------------------------------------------------
# Measured on the 20.7k-row catalog: a single cold /recommend costs ~139 ms
# (five sequential pgvector searches), but 100 concurrent requests for the SAME
# quiz all missed the cache simultaneously and all recomputed -> p95 3226 ms.
# That is a thundering herd, not a slow query: the work is duplicated 100x.
#
# Fix: one in-flight computation per cache key. The first caller computes; the
# others wait on the same lock and then re-read the cache, so they pay a Redis
# GET instead of five vector scans. `_INFLIGHT` is per-process, which is the
# right granularity here — with N workers the herd collapses from
# (concurrency) to (workers), and Redis absorbs the rest.
_INFLIGHT_GUARD = threading.Lock()
_INFLIGHT: dict[str, threading.Lock] = {}

# Wait budget for a follower blocked behind the leader's computation. Beyond
# this we recompute rather than queue indefinitely — a stuck leader must never
# turn into an availability outage for everyone else.
_SINGLEFLIGHT_TIMEOUT_S = 10.0


def _inflight_lock(key: str) -> threading.Lock:
    with _INFLIGHT_GUARD:
        lock = _INFLIGHT.get(key)
        if lock is None:
            lock = threading.Lock()
            _INFLIGHT[key] = lock
        return lock


def _release_inflight(key: str, lock: threading.Lock) -> None:
    lock.release()
    with _INFLIGHT_GUARD:
        # Only drop the entry if nobody else is queued behind it, otherwise a
        # waiter would end up holding a lock no longer in the registry and a
        # later caller would create a second lock for the same key.
        if not lock.locked() and _INFLIGHT.get(key) is lock:
            del _INFLIGHT[key]


def _read_cache(redis, cache_key: str) -> dict[str, Any] | None:
    try:
        cached = redis.get(cache_key)
    except Exception as exc:  # cache must never break the request
        logger.warning("redis read failed: %s", exc)
        return None
    if not cached:
        return None
    result = orjson.loads(cached)
    result["cached"] = True
    return result


def recommend(
    db: Session,
    quiz: dict[str, Any],
    categories: list[str] | None = None,
    use_cache: bool = True,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Run the full 3-stage pipeline and return ranked products per category.

    ``quiz`` shape::

        {styles: [..], color_palette: ["#HEX"], room_width_cm, room_length_cm,
         budget_min_toman, budget_max_toman, materials: [..], patterns: [..]}
    """
    categories = categories or CATEGORIES
    cache_key = quiz_cache_key({**quiz, "_categories": categories}, user_id)
    redis = get_redis()

    if not use_cache:
        return _compute(db, quiz, categories)

    hit = _read_cache(redis, cache_key)
    if hit is not None:
        return hit

    # Cache miss. Serialise concurrent misses for this key (see _INFLIGHT).
    lock = _inflight_lock(cache_key)
    acquired = lock.acquire(timeout=_SINGLEFLIGHT_TIMEOUT_S)
    if not acquired:
        logger.warning("single-flight wait timed out for %s; computing anyway", cache_key)
        return _compute(db, quiz, categories)
    try:
        # Re-check: the leader we queued behind has just populated the cache.
        hit = _read_cache(redis, cache_key)
        if hit is not None:
            return hit

        started = time.perf_counter()
        result = _compute(db, quiz, categories)
        try:
            redis.setex(cache_key, settings.RECOMMEND_CACHE_TTL, orjson.dumps(result))
        except Exception as exc:
            logger.warning("redis write failed: %s", exc)
        logger.info(
            "recommend cold compute key=%s took=%.0fms",
            cache_key, (time.perf_counter() - started) * 1000,
        )
        return result
    finally:
        _release_inflight(cache_key, lock)


def _compute(
    db: Session, quiz: dict[str, Any], categories: list[str]
) -> dict[str, Any]:
    """Run the actual 3-stage pipeline (uncached)."""
    user_emb = quiz.get("quiz_embedding") or get_embedding(
        quiz_to_text(
            quiz.get("styles", []),
            quiz.get("color_palette", []),
            quiz.get("materials", []),
            quiz.get("patterns", []),
        )
    )
    lo = int(quiz.get("budget_min_toman", 0))
    hi = int(quiz.get("budget_max_toman", 10**9))

    result_categories: dict[str, list[dict[str, Any]]] = {}
    for category in categories:
        if settings.is_postgres:
            scored_pairs = _stage_ab_postgres(db, category, lo, hi, user_emb)
        else:
            pool = _stage_a_hard_filter(db, category, lo, hi)
            scored_pairs = _stage_b_semantic(db, pool, user_emb)

        ranked = []
        for product, style_sim in scored_pairs:
            score = calculate_score(product, quiz, style_sim)
            ranked.append({**_product_payload(product), **score})
        ranked.sort(key=lambda r: r["final_score"], reverse=True)
        if ranked:
            result_categories[category] = ranked[:MAX_RESULTS]

    return {"categories": result_categories, "cached": False}
