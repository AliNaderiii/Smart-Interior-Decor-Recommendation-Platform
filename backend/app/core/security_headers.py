"""HTTP security headers middleware (OWASP A05 — Security Misconfiguration).

Phase 0B audit found **0 of 6** required headers on every response
(`docs/SECURITY_AUDIT_V2.md` §A05). This middleware adds them at the
application edge so the protection holds regardless of whether the app is
served behind Caddy, behind another proxy, or directly by uvicorn in dev.

The same headers are mirrored in the `Caddyfile`; defence in depth — if the
proxy config drifts, the app still emits them.

HSTS is only sent over TLS (or when explicitly forced), because sending
`Strict-Transport-Security` over plain HTTP is meaningless and pinning
localhost to HTTPS during development breaks the dev server.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.core.config import settings

#: Content-Security-Policy. `img-src` allows our S3/CDN + Unsplash demo assets;
#: `connect-src` allows the SPA to reach the API and the AI provider.
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "img-src 'self' data: blob: https://*.s3.ir-thr1.arvanstorage.ir https://images.unsplash.com; "
    "connect-src 'self' https://generativelanguage.googleapis.com; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)

STATIC_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
    "X-Permitted-Cross-Domain-Policies": "none",
}

HSTS = "max-age=63072000; includeSubDomains; preload"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach OWASP-recommended security headers to every response."""

    def __init__(self, app: ASGIApp, force_hsts: bool | None = None) -> None:
        super().__init__(app)
        # In production we always want HSTS (TLS is terminated at Caddy, so the
        # request reaching us may look like plain HTTP).
        self.force_hsts = (
            settings.APP_ENV == "production" if force_hsts is None else force_hsts
        )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        for header, value in STATIC_HEADERS.items():
            response.headers.setdefault(header, value)

        is_tls = request.url.scheme == "https" or (
            request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"
        )
        if self.force_hsts or is_tls:
            response.headers.setdefault("Strict-Transport-Security", HSTS)

        # Do not advertise the server stack (fingerprinting aid).
        response.headers["Server"] = settings.APP_NAME

        # Never let a browser or shared cache retain authenticated API payloads.
        if request.url.path.startswith(settings.API_V1_PREFIX):
            response.headers.setdefault("Cache-Control", "no-store")

        return response
