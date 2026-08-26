"""Designer project quota — Stage 1 (T-1.1).

Client spec: *"subscription required to create new projects."* Before this
module existed, ``POST /api/v1/projects`` created projects unconditionally, so
a free-tier designer could open unlimited projects — the plan dataset
(``seed_data/subscription_plans.json``, mirrored 1:1 by
``datasets/subscription_plans.json``) was decorative for the designer portal.

Rules (all values come from the versioned plans dataset — no magic numbers in
code):

* a designer's entitlement is the ``limits.projects`` of the plan id on their
  **active, unexpired** subscription; without one they fall back to
  ``designer_free`` (2 projects);
* ``-1`` means unlimited (``designer_agency``);
* an active subscription whose plan id cannot be resolved in the dataset
  (corrupt row, stale plan name) fails CLOSED to
  ``settings.DESIGNER_PROJECT_QUOTA_FALLBACK`` (1) — as does a known plan
  that lacks the quota field. Never open;
* ``admin`` callers are platform staff, not tenants: they are exempt (the same
  posture as ``require_designer`` itself, which already admits admins to every
  designer route). Homeowners have no projects at all and are stopped by the
  role guard upstream.

Race safety — two independent guards, so the check is atomic on every engine:

1. ``raise_for_quota_exhausted`` locks the designer's user row
   (``SELECT ... FOR UPDATE`` on PostgreSQL) *before* counting. On the
   production engine two concurrent creations by the same designer therefore
   serialise: the second transaction reads the count only after the first has
   committed.
2. ``insert_project_guarded`` performs the insert itself as
   ``INSERT ... SELECT ... WHERE (SELECT count) < quota`` — a single
   statement, atomic by construction even on SQLite (the dev fallback), where
   ``FOR UPDATE`` is a no-op and two connections could otherwise both read a
   stale count. The row lock (1) is what makes that statement's count fresh
   on PostgreSQL; the conditional insert (2) is the backstop that also holds
   on SQLite.

``create_designer_project`` combines both guards in a bounded retry loop: a
failed conditional insert is re-checked under the lock (a concurrent project
*delete* can free a slot between the check and the insert) and retried. The
function returns the new project or raises 402 — it never reports success for
a row that was not inserted.

User-facing strings are Persian-first (RTL) per the client contract; they are
centralised here (the backend has no i18n framework yet — this module is the
i18n-ready shape, mirroring ``frontend/src/lib/constants.ts``).
"""
from __future__ import annotations

from datetime import timezone

from fastapi import HTTPException, status
from sqlalchemy import bindparam, func, insert, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.datasets import designer_plan, designer_project_quota
from app.models.base import utcnow, uuid_pk
from app.models.project import Project
from app.models.user import User

#: ``-1`` in the plans dataset means "no limit".
UNLIMITED = -1

#: Free-tier fallback entitlement when no (active) subscription exists.
FALLBACK_PLAN_ID = "designer_free"

#: How many "check under lock -> conditional insert" rounds to attempt before
#: giving up with a 402. Three is far beyond any realistic contention burst
#: (a designer double-clicking) and keeps a hostile loop from spinning.
_MAX_CREATE_ATTEMPTS = 3

#: Quota-exhausted message. Persian-first; the rendered plan name and limit
#: come from the plans dataset, so the message can never disagree with the
#: enforcement.
QUOTA_EXHAUSTED_FA = (
    "سهمیهٔ پروژه‌های شما در پلن «{plan_name}» به پایان رسیده است "
    "(حداکثر {limit} پروژه). برای ایجاد پروژه‌های بیشتر، اشتراک خود را ارتقا دهید."
)


def _subscription_plan_state(user: User) -> str:
    """Classify the designer's subscription row.

    ``"none"``    — no row, inactive, or expired: the designer sits on the
                    free plan's dataset entitlement.
    ``"known"``   — active, unexpired, and the plan id exists in the dataset.
    ``"unknown"`` — active, unexpired, but the plan id cannot be resolved in
                    the dataset (corrupt row, stale plan name, or a homeowner
                    plan id on a designer account): fails closed to the
                    fallback quota.
    """
    sub = user.subscription
    if sub is None or not sub.is_active:
        return "none"
    expires = sub.expires_at
    if expires is not None:
        # SQLite hands back naive datetimes; PostgreSQL (timezone=True column)
        # returns aware ones. Normalise the same way public_share_view does
        # before comparing against the aware utcnow().
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= utcnow():
            return "none"  # expired = free account, not an active customer
    return "known" if designer_plan(sub.plan) else "unknown"


def active_subscription_plan(user: User) -> str | None:
    """The designer plan id this user is entitled to *right now*, or ``None``.

    Only counts when the subscription is active, unexpired **and** names a
    plan that exists in the dataset.
    """
    if _subscription_plan_state(user) != "known":
        return None
    return user.subscription.plan


def _effective_plan_name(user: User) -> str:
    """Display name for the 402 message: the active plan, else the free one."""
    plan_id = active_subscription_plan(user) or FALLBACK_PLAN_ID
    return designer_plan(plan_id).get("name_fa", "رایگان")


def designer_project_quota_for(user: User) -> int:
    """Project quota for ``user``: a positive int, or ``UNLIMITED``.

    * no usable subscription (none/expired) -> the free plan's dataset quota
      (2);
    * active subscription with a known plan -> that plan's dataset quota,
      with the fail-closed settings fallback (1) when ``limits.projects`` is
      missing from the dataset;
    * active subscription with an **unresolvable** plan id -> fail closed to
      ``settings.DESIGNER_PROJECT_QUOTA_FALLBACK`` (1): a corrupt row never
      inherits the free tier's dataset quota.
    """
    state = _subscription_plan_state(user)
    if state == "unknown":
        return int(settings.DESIGNER_PROJECT_QUOTA_FALLBACK)
    if state == "known":
        return designer_project_quota(user.subscription.plan)
    return designer_project_quota(FALLBACK_PLAN_ID)


def _quota_exceeded_error(user: User) -> HTTPException:
    return HTTPException(
        status.HTTP_402_PAYMENT_REQUIRED,
        QUOTA_EXHAUSTED_FA.format(
            plan_name=_effective_plan_name(user),
            limit=designer_project_quota_for(user),
        ),
    )


def raise_for_quota_exhausted(user: User, db: Session) -> None:
    """Raise 402 (Persian) when ``user`` has used up their project quota.

    Layer 1 of the race-safe check: locks the designer row first so the count
    is taken under the lock (PostgreSQL) — see module docstring.
    """
    if user.role != "designer" or designer_project_quota_for(user) == UNLIMITED:
        return
    db.execute(select(User).where(User.id == user.id).with_for_update())
    existing = db.scalar(
        select(func.count(Project.id)).where(Project.designer_id == user.id)
    )
    if existing is not None and existing >= designer_project_quota_for(user):
        raise _quota_exceeded_error(user)


def insert_project_guarded(
    db: Session, designer_id: str, values: dict[str, object], quota: int
) -> bool:
    """Atomically insert a project row, but only while ``count < quota``.

    Layer 2 of the race-safe check: ``INSERT ... SELECT ... WHERE
    (SELECT count) < quota`` is a single statement, so it cannot interleave
    with a concurrent creation on any engine. Returns True when the row was
    inserted; False when the quota was reached first (the caller then raises
    the 402 via :func:`raise_for_quota_exhausted`).

    ``values`` must be the scalar project fields *including* ``id`` (so the
    caller can fetch the row after commit) — do not pass relationship or
    server-default fields.
    """
    count_subq = (
        select(func.count(Project.id))
        .where(Project.designer_id == designer_id)
        .correlate(None)
        .scalar_subquery()
    )
    stmt = insert(Project).from_select(
        list(values.keys()),
        select(
            *[bindparam(f"quota_{name}", value=value) for name, value in values.items()]
        ).where(count_subq < quota),
    )
    result = db.execute(stmt)
    return bool(result.rowcount)


def create_designer_project(
    db: Session, user: User, values: dict[str, object]
) -> Project | None:
    """Create a project for a designer under the quota guards.

    ``values`` is the request body fields (name/client_name/client_email/
    notes); the id and designer_id are added here.

    * non-designer (admin) -> ``None``: no quota applies, the caller does a
      plain insert;
    * unlimited plan (``-1``) -> plain insert, returns the project;
    * finite quota -> guarded loop (module docstring): returns the new
      project, or raises 402 (Persian message) when the quota is used up.
    """
    if user.role != "designer":
        return None
    values = {**values, "id": uuid_pk(), "designer_id": user.id}
    quota = designer_project_quota_for(user)
    if quota == UNLIMITED:
        project = Project(**values)
        db.add(project)
        db.commit()
        return project
    for _ in range(_MAX_CREATE_ATTEMPTS):
        raise_for_quota_exhausted(user, db)
        if insert_project_guarded(db, user.id, values, quota):
            db.commit()
            return db.get(Project, values["id"])
    # Give up only after repeated under-lock re-checks: raise the exact 402.
    # (A concurrent delete that freed a slot in the final microsecond makes
    # this request a 402 that the next click succeeds on — the safe
    # direction, and it cannot produce a phantom success.)
    raise_for_quota_exhausted(user, db)
    raise _quota_exceeded_error(user)
