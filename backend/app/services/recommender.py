"""Three-stage hybrid recommendation engine (ADR-005).

Stage A — Hard filter (SQL): room_type + category + budget window + is_verified.
Stage B — Semantic candidate retrieval: pgvector cosine distance
          ``style_embedding <=> :user_embedding LIMIT 100`` on Postgres;
          Python cosine fallback on SQLite (tests).
Stage C — Weighted scoring with full explainability:
          final = 0.30*style + 0.30*color + 0.20*budget + 0.15*material + 0.05*pattern

Results are cached in Redis under ``rec:{sha256(quiz-payload)}`` TTL 3600s.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select
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
def quiz_cache_key(quiz: dict[str, Any]) -> str:
    """Stable Redis key for a quiz payload."""
    canonical = json.dumps(quiz, sort_keys=True, default=str)
    return "rec:" + hashlib.sha256(canonical.encode()).hexdigest()


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
    """Stages A+B fused in one pgvector query (production path)."""
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


def recommend(
    db: Session,
    quiz: dict[str, Any],
    categories: list[str] | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Run the full 3-stage pipeline and return ranked products per category.

    ``quiz`` shape::

        {styles: [..], color_palette: ["#HEX"], room_width_cm, room_length_cm,
         budget_min_toman, budget_max_toman, materials: [..], patterns: [..]}
    """
    categories = categories or CATEGORIES
    cache_key = quiz_cache_key({**quiz, "_categories": categories})
    redis = get_redis()

    if use_cache:
        try:
            cached = redis.get(cache_key)
            if cached:
                result = json.loads(cached)
                result["cached"] = True
                return result
        except Exception as exc:  # cache must never break the request
            logger.warning("redis read failed: %s", exc)

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

    result = {"categories": result_categories, "cached": False}
    if use_cache:
        try:
            redis.setex(cache_key, settings.RECOMMEND_CACHE_TTL, json.dumps(result))
        except Exception as exc:
            logger.warning("redis write failed: %s", exc)
    return result
