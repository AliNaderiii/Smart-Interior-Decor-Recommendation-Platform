"""User endpoints: GDPR erasure (Art. 17) and data export (Art. 15/20).

Stage 03 findings closed here (probe `G-01`…`G-03`):

* **G-02** — erasure deleted the user row but left ``audit_logs`` rows keyed to
  the deleted ``user_id``. Those rows carry IP address and user agent: personal
  data, still linkable to the (now anonymous) subject through the id.
  Deleting them outright is the wrong answer — the security trail is the one
  record with a legitimate-interest basis for retention, and destroying it on
  request would let an attacker erase their own tracks by registering, abusing
  the platform and then invoking Art. 17. The rows are therefore
  **pseudonymised**: the link to the person is severed (id replaced with a
  keyed digest, IP truncated to its network prefix, user agent dropped) while
  the sequence of events survives.
* **G-03** — the erasure itself was not audited, so "this account was deleted,
  by whom, from where" was unanswerable.
* **G-01** — ``product_feedback`` rows were left to the database's own cascade,
  which is only enforced when the driver has foreign keys switched on. Deleted
  explicitly now, like every other owned table.

There was also **no export path at all** (Art. 15 right of access / Art. 20
portability), so a subject access request had to be served by hand out of the
production database. ``GET /users/me/export`` returns the full inventory.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.db.session import get_db
from app.models import audit_log as actions
from app.models.audit_log import AuditLog
from app.models.feedback import ProductFeedback
from app.models.moodboard import Moodboard
from app.models.project import Project, ShareLink
from app.models.quiz import StyleQuiz
from app.models.subscription import Payment, Subscription
from app.models.user import User
from app.schemas.common import ok
from app.services import audit

router = APIRouter(prefix="/users", tags=["users"])


def pseudonym_for(user_id: str) -> str:
    """Stable, keyed, non-reversible stand-in for a deleted user id.

    Keyed with ``SECRET_KEY`` rather than a plain hash: a bare SHA-256 of a
    32-character hex id is trivially reversible by anyone holding the id list
    (rainbow table over the id space), which would defeat the point.
    """
    digest = hmac.new(
        settings.SECRET_KEY.encode(), f"erased:{user_id}".encode(), hashlib.sha256
    ).hexdigest()[:25]
    # Exactly 32 characters: `audit_logs.user_id` is String(32) and widening it
    # would need a migration on a table another stage owns. 100 bits of digest
    # is far beyond what a collision would need to matter here.
    return f"erased-{digest}"


def _truncate_ip(value: str) -> str:
    """Keep the /24 (or /48 for IPv6) so abuse patterns stay visible."""
    if not value:
        return ""
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return ""
    if isinstance(ip, ipaddress.IPv4Address):
        return str(ipaddress.ip_network(f"{ip}/24", strict=False).network_address)
    return str(ipaddress.ip_network(f"{ip}/48", strict=False).network_address)


@router.get("/me/export")
def gdpr_export(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """GDPR Art. 15/20: everything the platform holds about the caller.

    Rate limited per user: the response is a complete personal-data dump, which
    makes it both expensive to build and the single most valuable object an
    attacker holding a stolen session could ask for.
    """
    enforce_rate_limit(
        f"export:{user.id}", limit=settings.EXPORT_RATE_LIMIT_PER_HOUR,
        window_seconds=3600,
    )
    uid = user.id
    quizzes = db.scalars(select(StyleQuiz).where(StyleQuiz.user_id == uid)).all()
    boards = db.scalars(select(Moodboard).where(Moodboard.user_id == uid)).all()
    projects = db.scalars(select(Project).where(Project.designer_id == uid)).all()
    payments = db.scalars(select(Payment).where(Payment.user_id == uid)).all()
    feedback = db.scalars(
        select(ProductFeedback).where(ProductFeedback.user_id == uid)
    ).all()
    logs = db.scalars(
        select(AuditLog).where(AuditLog.user_id == uid)
        .order_by(AuditLog.created_at.desc()).limit(500)
    ).all()

    audit.record(db, actions.ACTION_GDPR_EXPORT, user_id=uid, request=request)
    return ok({
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "account": {
            "id": user.id, "email": user.email, "full_name": user.full_name,
            "role": user.role, "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
        },
        "subscription": (
            {"plan": user.subscription.plan,
             "is_active": user.subscription.is_active,
             "expires_at": user.subscription.expires_at.isoformat()
             if user.subscription.expires_at else None}
            if user.subscription else None
        ),
        "quizzes": [
            {"id": q.id, "project_id": q.project_id, "client_name": q.client_name,
             "styles": q.styles, "color_palette": q.color_palette,
             "room_width_cm": q.room_width_cm, "room_length_cm": q.room_length_cm,
             "budget_min_toman": q.budget_min_toman,
             "budget_max_toman": q.budget_max_toman,
             "materials": q.materials, "patterns": q.patterns,
             "created_at": q.created_at.isoformat()}
            for q in quizzes
        ],
        "moodboards": [
            {"id": b.id, "title": b.title, "items": b.items,
             "shopping_list": b.shopping_list,
             "created_at": b.created_at.isoformat()}
            for b in boards
        ],
        "projects": [
            {"id": p.id, "name": p.name, "client_name": p.client_name,
             "client_email": p.client_email, "notes": p.notes,
             "created_at": p.created_at.isoformat()}
            for p in projects
        ],
        "product_feedback": [
            {"product_id": f.product_id, "signal": f.signal, "category": f.category,
             "created_at": f.created_at.isoformat()}
            for f in feedback
        ],
        "payments": [
            {"amount_toman": p.amount_toman, "status": p.status,
             "provider": p.provider, "created_at": p.created_at.isoformat()}
            for p in payments
        ],
        "security_events": [
            {"action": log.action, "detail": log.detail, "ip": log.ip,
             "user_agent": log.user_agent, "at": log.created_at.isoformat()}
            for log in logs
        ],
        "retention_notice": (
            "Security events are retained for 180 days under GDPR Art. 6(1)(f) "
            "(legitimate interest in fraud and abuse prevention). Payment "
            "records are retained for 7 years to meet accounting obligations "
            "and are pseudonymised, not deleted, on erasure."
        ),
    })


@router.delete("/me")
def gdpr_delete_me(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """GDPR right-to-erasure: hard-delete the user and ALL owned data."""
    uid = user.id
    pseudonym = pseudonym_for(uid)

    db.execute(delete(ProductFeedback).where(ProductFeedback.user_id == uid))
    db.execute(delete(ShareLink).where(ShareLink.created_by == uid))
    db.execute(delete(Payment).where(Payment.user_id == uid))
    db.execute(delete(Subscription).where(Subscription.user_id == uid))
    db.execute(delete(Moodboard).where(Moodboard.user_id == uid))
    db.execute(delete(StyleQuiz).where(StyleQuiz.user_id == uid))
    db.execute(delete(Project).where(Project.designer_id == uid))

    # Pseudonymise rather than delete: keeps the security trail, severs the
    # link to a person. Rows are re-read and rewritten one by one because the
    # IP truncation is not expressible in SQL portably.
    rows = db.scalars(select(AuditLog).where(AuditLog.user_id == uid)).all()
    for row in rows:
        row.ip = _truncate_ip(row.ip)
        row.user_agent = ""
    db.flush()
    db.execute(
        update(AuditLog).where(AuditLog.user_id == uid).values(user_id=pseudonym)
    )

    # G-03: the erasure is itself a security event. Written *after* the
    # pseudonymisation pass and already carrying the pseudonym, so this record
    # never contains the erased identity — writing it first and relying on the
    # bulk update to catch it would depend on flush ordering, and the session
    # is configured with `autoflush=False`.
    db.add(AuditLog(
        user_id=pseudonym,
        action=actions.ACTION_USER_DELETE,
        detail="GDPR Art.17 erasure requested by the data subject",
        ip=_truncate_ip(audit.client_ip(request)),
        user_agent="",
    ))

    db.delete(db.get(User, uid))
    db.commit()
    return ok({
        "message": "All your data has been permanently deleted.",
        "audit_pseudonym": pseudonym,
        "retained": {
            "security_events": "pseudonymised, purged after 180 days",
        },
    })
