"""Email abstraction — mock (log) for MVP, Resend-ready via env."""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, html: str) -> bool:
    """Send an email via the configured provider. Returns success bool."""
    if settings.EMAIL_PROVIDER == "resend" and settings.RESEND_API_KEY:
        try:
            resp = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": settings.EMAIL_FROM,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
                timeout=30,
            )
            return resp.status_code in (200, 201)
        except httpx.HTTPError as exc:
            logger.error("resend failed: %s", exc)
            return False
    logger.info("[mock email] to=%s subject=%r", to, subject)
    return True
