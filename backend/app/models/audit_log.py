"""Audit log (OWASP A09 — Security Logging & Monitoring Failures).

Phase 0B found no forensic trail at all: the 8-attempt brute-force probe in
`docs/SECURITY_AUDIT_V2.md` §A07 left zero evidence behind. This table records
security-relevant events so an incident can be reconstructed.

Deliberately append-only in practice (no update path in the app) and written
on a best-effort basis — an audit write must never break a user request.
"""
from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPk

# Canonical action names — keep stable, they are queried by ops.
ACTION_LOGIN = "login"
ACTION_LOGIN_FAILED = "login_failed"
ACTION_LOGIN_BLOCKED = "login_blocked"
ACTION_LOGOUT = "logout"
ACTION_REGISTER = "register"
ACTION_TOKEN_REFRESH = "token_refresh"
ACTION_USER_DELETE = "user_delete"
ACTION_SHARE_CREATE = "share_create"
ACTION_PROJECT_DELETE = "project_delete"
ACTION_MOODBOARD_DELETE = "moodboard_delete"
ACTION_ROLE_CHANGE = "role_change"
ACTION_PRODUCT_VERIFY = "product_verify"


class AuditLog(Base, UUIDPk, TimestampMixin):
    __tablename__ = "audit_logs"

    #: Nullable: failed logins and blocked attempts have no authenticated user.
    user_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    #: Free-form context (target id, email attempted, reason). Never secrets.
    detail: Mapped[str] = mapped_column(String(500), default="")
    ip: Mapped[str] = mapped_column(String(45), default="")  # IPv6-safe length
    user_agent: Mapped[str] = mapped_column(String(255), default="")

    __table_args__ = (
        # Hot path: "show me everything that happened to this user recently"
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        # Hot path: "show me all failed logins in the last 15 minutes"
        Index("ix_audit_logs_action_created", "action", "created_at"),
    )
