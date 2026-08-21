"""httpOnly cookie auth (OWASP A02 — Cryptographic Failures).

Phase 0B probe: login returned tokens in the JSON body only, with no
`Set-Cookie` at all, so any XSS could exfiltrate both access and refresh
tokens (`docs/SECURITY_AUDIT_V2.md` §A02).

V2 sets both tokens as `HttpOnly; Secure; SameSite=Strict` cookies. Because
the tokens are then sent automatically by the browser, we add a
**double-submit CSRF token**: a non-HttpOnly cookie the SPA reads and echoes
in the `X-CSRF-Token` header. An attacker on another origin can cause the
cookie to be sent but cannot read it to set the header.

`USE_COOKIE_AUTH=false` keeps the v1 body-token behaviour for local dev and
for the existing test-suite/tooling.
"""
from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, Response, status

from app.core.config import settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def _cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "path": "/",
    }


def set_auth_cookies(response: Response, access: str, refresh: str) -> str:
    """Attach access/refresh/CSRF cookies. Returns the CSRF token."""
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **_cookie_kwargs(),
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        **_cookie_kwargs(),
    )
    csrf = secrets.token_urlsafe(32)
    # Readable by JS on purpose — that is the whole point of double-submit.
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )
    return csrf


def clear_auth_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/")


def verify_csrf(request: Request) -> bool:
    """Double-submit check. True when not using cookie auth (nothing to forge)."""
    if not settings.USE_COOKIE_AUTH:
        return True
    # Bearer callers (mobile, CI, curl) are not cookie-driven -> not CSRF-able.
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return True
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header:
        return False
    return secrets.compare_digest(cookie, header)


def require_csrf_for_cookie_session(request: Request) -> None:
    """Enforce double-submit on endpoints that do not resolve a current user.

    Stage 03 (T-09). ``get_current_user`` performs this check, so every
    authenticated state change was covered — but ``/auth/refresh`` and
    ``/auth/logout`` deliberately do *not* require a valid access token (that
    is the point of a refresh endpoint), so they were protected by
    ``SameSite=Strict`` alone. ``COOKIE_SAMESITE`` is configuration, and a
    deployment that legitimately needs ``none`` (SPA on a different origin from
    the API) would have silently lost CSRF protection on the one endpoint that
    mints new credentials. The check is cheap; make it unconditional.
    """
    if not settings.USE_COOKIE_AUTH:
        return
    # No auth cookie present -> the caller is not riding an ambient session.
    if not request.cookies.get(REFRESH_COOKIE) and not request.cookies.get(ACCESS_COOKIE):
        return
    if not verify_csrf(request):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid"
        )
