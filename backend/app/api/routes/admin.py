"""Admin: users, subscriptions, style taxonomy, pending verifications.

Stage 03 hardening (probe `A-06`, `V-04`, `L-01`):
  * ``UserPatch`` rejects unknown fields — it was an open model on the single
    most privileged write in the API
  * an admin cannot change its own role or deactivate itself (self-lockout, and
    the audit trail of "who demoted whom" becomes meaningless if the actor and
    the target can be the same principal without a record)
  * role changes and activation changes are audited with actor, target and the
    old -> new transition; ``ACTION_ROLE_CHANGE`` existed as a constant but was
    never written by any code path

P4-B (2026-09-09): ``DELETE /admin/users/{user_id}`` — administrative account
erasure. Same cascade and audit-trail pseudonymisation as the data subject's
own ``DELETE /users/me`` (one implementation, ``app/services/erasure.py``),
plus the two guards ``PATCH`` already enforces: no self-deletion and never
the last active administrator. Until this route existed the only way to
remove an account was the owner's own password, so throwaway probe accounts
accumulated in the live database with no lawful way to purge them.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import audit_log as actions
from app.models.product import MATERIALS, STYLES, Product
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.common import ok
from app.services import audit, catalog_integrity
from app.services.erasure import erase_account

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return ok([
        {
            "id": u.id, "email": u.email, "full_name": u.full_name,
            "role": u.role, "is_active": u.is_active,
            "subscription_plan": u.subscription.plan if u.subscription else "free",
            "subscription_active": bool(u.subscription and u.subscription.is_active),
            "created_at": u.created_at.isoformat(),
        }
        for u in rows
    ])


class UserPatch(BaseModel):
    #: V-04: this model feeds the highest-privilege write in the product. An
    #: unknown key here is a client bug or an attack, never something to drop
    #: silently — and `extra="forbid"` is what stops a future column from
    #: becoming remotely settable the day it is added.
    model_config = ConfigDict(extra="forbid")

    is_active: bool | None = None
    role: str | None = Field(default=None, pattern="^(homeowner|designer|admin)$")


@router.patch("/users/{user_id}")
def patch_user(
    user_id: str,
    body: UserPatch,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # A-06: separation of duties. Self-service demotion is either a mistake
    # (locking the last admin out of the platform) or an attempt to launder a
    # privilege change; either way another admin must make the call.
    if user.id == admin.id and (body.role is not None or body.is_active is False):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An admin cannot change its own role or deactivate itself",
        )

    changes: list[str] = []
    if body.is_active is not None and body.is_active != user.is_active:
        changes.append(f"is_active {user.is_active}->{body.is_active}")
        user.is_active = body.is_active
    if body.role is not None and body.role != user.role:
        # Never let the platform reach zero usable administrators.
        if user.role == "admin" and body.role != "admin":
            remaining = db.scalar(
                select(func.count(User.id)).where(
                    User.role == "admin", User.is_active.is_(True), User.id != user.id
                )
            )
            if not remaining:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Refusing to remove the last active administrator",
                )
        changes.append(f"role {user.role}->{body.role}")
        user.role = body.role

    db.commit()
    if changes:
        audit.record(
            db, actions.ACTION_ROLE_CHANGE, user_id=admin.id,
            detail=f"target={user.id} {'; '.join(changes)}", request=request,
        )
    return ok({"id": user.id, "role": user.role, "is_active": user.is_active})


def _count_other_active_admins(db: Session, user_id: str) -> int:
    return int(db.scalar(
        select(func.count(User.id)).where(
            User.role == "admin", User.is_active.is_(True), User.id != user_id
        )
    ) or 0)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    request: Request,
    reason: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Erase an account and everything it owns; pseudonymise its audit trail.

    * ``404`` unknown id — the same response as for any other missing resource
      so the route cannot be used to enumerate ids.
    * ``409`` self-deletion — an administrator erasing itself is either a
      mistake or an attempt to leave no accountable actor behind; another
      administrator must do it (A-06 separation of duties, as for ``PATCH``).
    * ``409`` last active administrator — the platform must always keep
      someone who can administer it.

    Two audit rows result: ``user_delete`` under the erased account's
    pseudonym (identical to self-service erasure) and ``user_delete`` under the
    actor's id naming the target by pseudonym and keyed e-mail digest only.
    The erased user's tokens die with the row (`get_current_user` resolves the
    subject on every request and refuses an unknown id).
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An admin cannot delete its own account; ask another administrator",
        )
    # Unreachable over HTTP today — the actor is always *another* active admin,
    # so at least one remains — but the invariant must not depend on how the
    # caller was authenticated (a future service principal, a CLI, a test).
    if user.role == "admin" and user.is_active and not _count_other_active_admins(db, user.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Refusing to remove the last active administrator",
        )

    receipt = erase_account(db, user, request=request, actor_id=admin.id, reason=reason)
    return ok({
        "id": receipt.user_id,
        "audit_pseudonym": receipt.pseudonym,
        "email_pseudonym": receipt.email_pseudonym,
        "audit_rows_pseudonymised": receipt.audit_rows_pseudonymised,
        "redis_keys_purged": receipt.redis_keys_purged,
    })


@router.get("/subscriptions")
def list_subscriptions(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.execute(
        select(Subscription, User.email).join(User, Subscription.user_id == User.id)
    ).all()
    return ok([
        {
            "id": s.id, "user_email": email, "plan": s.plan, "is_active": s.is_active,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
        }
        for s, email in rows
    ])


@router.get("/taxonomy")
def get_taxonomy(_: User = Depends(require_admin)):
    return ok({"styles": STYLES, "materials": MATERIALS})


@router.get("/stats")
def stats(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return ok({
        "users": db.scalar(select(func.count(User.id))),
        "products": db.scalar(select(func.count(Product.id))),
        "verified_products": db.scalar(
            select(func.count(Product.id)).where(Product.is_verified.is_(True))
        ),
        "pending_products": db.scalar(
            select(func.count(Product.id)).where(Product.is_verified.is_(False))
        ),
        "active_subscriptions": db.scalar(
            select(func.count(Subscription.id)).where(Subscription.is_active.is_(True))
        ),
        # ADR-016: verified rows the integrity gate currently excludes, and
        # the policy/mode that produced the verdicts.
        "integrity_excluded_products": db.scalar(
            select(func.count(Product.id)).where(
                Product.is_verified.is_(True), Product.integrity_ok.is_(False)
            )
        ),
        "catalog_integrity": catalog_integrity.summary(db),
    })
