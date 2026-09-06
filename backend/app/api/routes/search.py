"""Visual search endpoint (ADR-013) — ``POST /api/v1/search/visual``.

Multipart upload of one photo → the catalogue items that look most like it.
The image goes through the same hardened validator as admin product uploads
(magic-byte sniffing, size/pixel bounds, re-encoding), is embedded or
palette-analysed **in memory**, and is then discarded: no storage write, no
database row, no cache entry. The response echoes the extracted palette so
the user can see what the search "saw" and hand the swatches to the quiz.

Free users get the same paywall shape as ``/recommend``: the top hit per
category is fully visible, the rest are teasers — the value is shown, the
door is not slammed (ADR-011).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from ai.taxonomy import categories as taxonomy_categories
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.datasets import recommendation_limit
from app.core.rate_limit import enforce_rate_limit
from app.core.uploads import validate_image_upload
from app.db.session import get_db
from app.models import audit_log as actions
from app.models.user import User
from app.schemas.common import ok
from app.services import audit, visual_search

router = APIRouter(prefix="/search", tags=["search"])

#: Hard cap on ``limit`` — a visual search is a shortlist, not an export.
MAX_LIMIT = 24
#: Teaser fields for locked items (mirrors the /recommend paywall).
_TEASER_KEYS = ("id", "title", "title_fa", "category", "image_url", "similarity")


@router.post("/visual")
def visual_search_endpoint(
    request: Request,
    file: UploadFile = File(...),
    category: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=12, ge=1, le=MAX_LIMIT),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Find catalogue products that look like the uploaded photo.

    * ``category`` — optional taxonomy id (``sofa``, ``rug`` …) to search one
      shelf only; anything outside the taxonomy is a 422, not a silent empty.
    * ``limit`` — 1-24 items across categories (default 12).
    """
    # Costs an embedding + a vector query per call: throttled like an upload,
    # not like a cached /recommend hit.
    enforce_rate_limit(
        f"visual-search:{user.id}", limit=settings.VISUAL_SEARCH_RATE_LIMIT_PER_MINUTE
    )
    if category is not None and category not in taxonomy_categories():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Unknown category {category!r}; expected one of {sorted(taxonomy_categories())}",
        )

    try:
        image = validate_image_upload(file)
    except HTTPException as exc:
        audit.record(
            db, actions.ACTION_UPLOAD_REJECTED, user_id=user.id,
            detail=f"visual-search status={exc.status_code} reason={str(exc.detail)[:120]}",
            request=request,
        )
        raise

    result = visual_search.search(db, image.data, category=category, limit=limit)

    # Paywall (ADR-011): free users see the best match per category in full,
    # the rest as teasers — enforced here, not in the UI.
    sub = user.subscription
    is_pro = bool(sub and sub.is_active)
    if not is_pro:
        visible_limit = recommendation_limit("homeowner_free")
        seen: dict[str, int] = {}
        items = []
        for item in result["items"]:
            n = seen.get(item["category"], 0)
            seen[item["category"]] = n + 1
            if n < visible_limit:
                items.append(item)
            else:
                items.append({**{k: item[k] for k in _TEASER_KEYS if k in item}, "locked": True})
        result["items"] = items
    result["is_pro"] = is_pro
    result["meta"]["query_image"] = {
        "width": image.width,
        "height": image.height,
        "content_type": image.content_type,
    }
    return ok(result)
