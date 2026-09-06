"""Behavioural events (ADR-014): ``POST /events`` (batch ingest) and
``GET /admin/events/summary`` (funnel per category).

What this is: the capture side of ``docs/ai/feedback-events.md`` — the data a
future learning stage needs, recorded correctly from day one (impressions as
the denominator, position and weights_version on every row).

What this is NOT: no ranking code reads this table. The recommender's
feedback stage is still the bounded, transparent thumbs re-rank, and the
summary endpoint is a report, not a model.

Write-path rules (spec §2):

* **never fail the user's request** — a bad product id in a batch drops that
  event, a storage error is logged and swallowed; the response is always
  ``202 {accepted, dropped}``;
* rate-limited per user/session so an open tab cannot flood the table;
* no PII, no free text — the schema is a closed vocabulary plus ids.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import bearer, get_current_user, require_admin
from app.core.config import settings
from app.core.cookies import ACCESS_COOKIE
from app.core.rate_limit import enforce_rate_limit
from app.db.session import get_db
from app.models.feedback_event import EVENT_TYPES, FeedbackEvent
from app.models.product import Product
from app.models.user import User
from app.schemas.common import ok
from app.schemas.events import EventBatchIn

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])


def _optional_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """Resolve the caller if credentials are present, else ``None``.

    Anonymous share-page viewers legitimately emit events (spec: ``user_id``
    nullable, session id instead). When credentials ARE present they must be
    valid — a forged token is still a 401, never silently anonymous.
    """
    has_creds = creds is not None or (
        settings.USE_COOKIE_AUTH and request.cookies.get(ACCESS_COOKIE) is not None
    )
    if not has_creds:
        return None
    return get_current_user(request, creds, db)


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
def ingest_events(
    body: EventBatchIn,
    request: Request,
    user: User | None = Depends(_optional_user),
    db: Session = Depends(get_db),
):
    """Append a batch of behavioural events. Always 202 — see module docstring."""
    subject = user.id if user is not None else f"anon:{body.session_id}"
    enforce_rate_limit(f"events:{subject}", limit=settings.EVENTS_RATE_LIMIT_PER_MINUTE)

    wanted = {e.product_id for e in body.events}
    known = {
        pid: cat
        for pid, cat in db.execute(
            select(Product.id, Product.category).where(Product.id.in_(wanted))
        )
    }
    rows: list[FeedbackEvent] = []
    dropped = 0
    for e in body.events:
        category = known.get(e.product_id)
        if category is None:
            dropped += 1  # unknown product: not an error for the user, just noise
            continue
        rows.append(
            FeedbackEvent(
                user_id=user.id if user is not None else None,
                session_id=body.session_id,
                quiz_id=e.quiz_id,
                product_id=e.product_id,
                category=category,
                event_type=e.event_type,
                position=e.position,
                page_context=e.page_context,
                weights_version=e.weights_version,
            )
        )
    accepted = 0
    if rows:
        try:
            db.add_all(rows)
            db.commit()
            accepted = len(rows)
        except Exception as exc:  # pragma: no cover - defensive write path
            db.rollback()
            logger.warning("feedback_events write failed: %s: %s", type(exc).__name__, exc)
            dropped += len(rows)
    return ok({"accepted": accepted, "dropped": dropped})


@router.get("/admin/events/summary")
def events_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Per-category funnel over the last ``days`` days.

    ``ctr`` = clicks / impressions and ``like_rate`` = likes / impressions are
    reported only when there are impressions — a rate without a denominator
    is exactly the artefact the spec warns about. ``learning_ready`` restates
    the spec's honest threshold (≥ 10 000 events with impressions) so the
    dashboard never implies a model exists.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    counts = db.execute(
        select(FeedbackEvent.category, FeedbackEvent.event_type, func.count())
        .where(FeedbackEvent.created_at >= since)
        .group_by(FeedbackEvent.category, FeedbackEvent.event_type)
    ).all()
    by_cat: dict[str, dict[str, int]] = {}
    totals = dict.fromkeys(EVENT_TYPES, 0)
    for category, event_type, n in counts:
        by_cat.setdefault(category, dict.fromkeys(EVENT_TYPES, 0))[event_type] = int(n)
        totals[event_type] += int(n)

    def _rates(c: dict[str, int]) -> dict[str, float | None]:
        imp = c.get("impression", 0)
        return {
            "ctr": round(c.get("click", 0) / imp, 4) if imp else None,
            "like_rate": round(c.get("like", 0) / imp, 4) if imp else None,
            "dislike_rate": round(c.get("dislike", 0) / imp, 4) if imp else None,
            "save_rate": round(c.get("save", 0) / imp, 4) if imp else None,
        }

    sessions = db.scalar(
        select(func.count(func.distinct(FeedbackEvent.session_id)))
        .where(FeedbackEvent.created_at >= since)
    ) or 0
    total_events = sum(totals.values())
    return ok({
        "window_days": days,
        "since": since.isoformat(),
        "sessions": int(sessions),
        "total_events": total_events,
        "totals": {**totals, **_rates(totals)},
        "categories": [
            {"category": cat, **c, **_rates(c)}
            for cat, c in sorted(by_cat.items())
        ],
        # Spec §3: nothing learned is trustworthy below this; say so.
        "learning_ready": total_events >= 10_000 and totals["impression"] > 0,
        "learning_threshold_events": 10_000,
    })
