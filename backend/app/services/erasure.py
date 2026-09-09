"""Account erasure — one cascade shared by the data subject and the administrator.

Extracted from ``app/api/routes/users.py`` (Stage 03, probes G-01…G-03) when
the admin portal gained ``DELETE /admin/users/{id}``. Two copies of a
nine-table cascade drift the first time a table is added, and the second copy
is the one that forgets the pseudonymisation rules that make the first one
lawful — so there is exactly one.

Guarantees (unchanged from the Stage 03 route, now enforced for both callers):

* every owned row is deleted explicitly, never left to the database cascade —
  SQLite only enforces foreign keys when the driver switches them on, and a
  cascade that "usually" works is not a privacy guarantee;
* ``feedback_events`` rows are unlinked (``user_id -> NULL``), not deleted —
  they are aggregate funnel analytics with no PII (ADR-014);
* ``audit_logs`` rows are pseudonymised, never deleted: the security trail is
  the one record with a legitimate-interest basis for retention, and an
  attacker must not be able to erase their own tracks by invoking Art. 17;
* the erasure itself is audited under the pseudonym, so the record never
  re-introduces the identity it just erased. When an administrator performs
  the erasure a second row is written under the *actor's* id naming the
  target only by pseudonym and by a keyed, truncated e-mail digest —
  "who deleted whom, from where" stays answerable without keeping the e-mail;
* cached recommendations and rate-limit counters keyed by the user id are
  purged from Redis (S3-F002). A Redis outage never blocks the erasure; it is
  logged and reported in the receipt.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.log_redaction import pseudonymise_email
from app.models import audit_log as actions
from app.models.audit_log import AuditLog
from app.models.feedback import ProductFeedback
from app.models.feedback_event import FeedbackEvent
from app.models.moodboard import Moodboard
from app.models.project import Project, ShareLink
from app.models.quiz import StyleQuiz
from app.models.subscription import Payment, Subscription
from app.models.user import User
from app.services import audit

logger = logging.getLogger(__name__)

#: Written on the subject-side ``user_delete`` row so an auditor can tell a
#: self-service erasure from an administrative one without joining tables.
SELF_SERVICE_DETAIL = "GDPR Art.17 erasure requested by the data subject"
ADMIN_DETAIL = "account erased by an administrator"


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


def truncate_ip(value: str) -> str:
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


@dataclass(frozen=True)
class ErasureReceipt:
    """What the caller may safely echo back: nothing here identifies the person."""

    user_id: str
    pseudonym: str
    #: ``v***@example.com#a1b2c3d4`` — the same keyed form the log redactor
    #: uses, so an administrator can recognise *which* account went without
    #: the plaintext address surviving anywhere.
    email_pseudonym: str
    role: str
    audit_rows_pseudonymised: int
    #: ``None`` when Redis was unreachable (logged; the erasure still stands).
    redis_keys_purged: int | None


def erase_account(
    db: Session,
    user: User,
    *,
    request: Request | None,
    actor_id: str | None = None,
    reason: str | None = None,
) -> ErasureReceipt:
    """Hard-delete ``user`` and every owned row; pseudonymise the audit trail.

    ``actor_id`` is ``None`` for self-service erasure (``DELETE /users/me``)
    and the administrator's id for ``DELETE /admin/users/{id}``. The whole
    cascade, both audit rows and the user row go in ONE transaction: an
    erasure that is half-applied is worse than one that failed.
    """
    uid = user.id
    pseudonym = pseudonym_for(uid)
    email_pseudonym = pseudonymise_email(user.email)
    role = user.role
    note = f" reason={reason.strip()[:200]}" if reason and reason.strip() else ""

    db.execute(delete(ProductFeedback).where(ProductFeedback.user_id == uid))
    # ADR-014: behavioural rows are aggregate analytics data with no PII; sever
    # the link to the person (user_id -> NULL, the FK is a user id so it cannot
    # hold the pseudonym) rather than deleting the funnel history.
    db.execute(
        update(FeedbackEvent).where(FeedbackEvent.user_id == uid).values(user_id=None)
    )
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
        row.ip = truncate_ip(row.ip)
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
        detail=(SELF_SERVICE_DETAIL if actor_id is None else ADMIN_DETAIL) + note,
        ip=truncate_ip(audit.client_ip(request)),
        user_agent="",
    ))
    if actor_id is not None:
        # Accountability row for the administrator. The actor is not the one
        # being erased, so their IP / user agent are kept in full exactly as
        # `ACTION_ROLE_CHANGE` keeps them; the target appears only as the
        # pseudonym and the keyed e-mail digest.
        db.add(AuditLog(
            user_id=actor_id,
            action=actions.ACTION_USER_DELETE,
            detail=f"target={pseudonym} email={email_pseudonym} role={role}{note}"[:500],
            ip=audit.client_ip(request),
            user_agent=audit.user_agent(request),
        ))

    db.delete(db.get(User, uid))
    db.commit()

    return ErasureReceipt(
        user_id=uid,
        pseudonym=pseudonym,
        email_pseudonym=email_pseudonym,
        role=role,
        audit_rows_pseudonymised=len(rows),
        redis_keys_purged=_purge_redis(uid, pseudonym),
    )


def _purge_redis(uid: str, pseudonym: str) -> int | None:
    """S3-F002: drop cached recommendations and rate-limit buckets for ``uid``.

    Returns the number of keys removed, or ``None`` when Redis was not
    reachable — the erasure has already been committed by then and must not be
    reported as failed because a cache was down.
    """
    try:
        from app.core.redis_client import get_redis

        redis = get_redis()
        keys: set[str] = {f"export:{uid}", f"rl:rec:{uid}", f"rl:export:{uid}"}
        keys.update(_as_str(k) for k in redis.scan_iter(f"rec:{uid}:*"))
        keys.update(_as_str(k) for k in redis.scan_iter(f"rl:*{uid}*"))
        removed = 0
        for key in keys:
            removed += int(redis.delete(key) or 0)
        return removed
    except Exception as exc:
        logger.warning(
            "Failed to purge Redis cache/rate-limit keys for erased user %s: %s",
            pseudonym,
            exc,
        )
        return None


def _as_str(key: object) -> str:
    return key.decode() if isinstance(key, bytes) else str(key)
