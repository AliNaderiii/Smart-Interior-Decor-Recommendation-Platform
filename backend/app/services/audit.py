"""Audit-log writer + client IP extraction.

Best-effort by design: a failure to write an audit row must never turn a
successful user action into a 500. Failures are logged and swallowed.
"""
from __future__ import annotations

import logging

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def client_ip(request: Request | None) -> str:
    """Best-effort client IP, honouring a single trusted proxy hop."""
    if request is None:
        return ""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        # Left-most entry is the original client.
        return forwarded.split(",")[0].strip()[:45]
    return (request.client.host if request.client else "")[:45]


def user_agent(request: Request | None) -> str:
    if request is None:
        return ""
    return request.headers.get("user-agent", "")[:255]


def record(
    db: Session,
    action: str,
    *,
    user_id: str | None = None,
    detail: str = "",
    request: Request | None = None,
    commit: bool = True,
) -> None:
    """Append one audit row. Never raises."""
    try:
        db.add(
            AuditLog(
                user_id=user_id,
                action=action,
                detail=detail[:500],
                ip=client_ip(request),
                user_agent=user_agent(request),
            )
        )
        if commit:
            db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("audit log write failed for action=%s: %s", action, exc)
        try:
            db.rollback()
        except Exception:
            pass
