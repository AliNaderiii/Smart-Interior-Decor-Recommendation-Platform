"""HTTP security headers middleware (OWASP A05 — Security Misconfiguration).

Phase 0B audit found **0 of 6** required headers on every response
(`docs/SECURITY_AUDIT_V2.md` §A05). V2 added this middleware. Stage 03 closes
three gaps the V2 implementation still had, each verified by probe:

* **H-01 — the 500 path had no headers at all.** ``BaseHTTPMiddleware`` re-raises
  whatever ``call_next`` raises, so an unhandled exception propagated past this
  middleware to Starlette's outermost ``ServerErrorMiddleware``. That response —
  the plain-text ``Internal Server Error`` an attacker sees while probing —
  carried no CSP, no ``X-Frame-Options``, no ``nosniff``. The middleware now
  owns its own failure path and converts it to the standard JSON envelope.
* **T-41 — ``script-src 'unsafe-inline'``** made the CSP useless as an XSS
  backstop. The Vite build emits no inline ``<script>`` (only
  ``<script type="module" src=…>``), so the directive was pure attack surface.
* **IR-005 — ``img-src`` was pinned to a hard-coded Arvan bucket host** that does
  not necessarily match the configured ``S3_PUBLIC_BASE_URL``. It is now derived
  from configuration.

The same headers are mirrored in the `Caddyfile`; defence in depth — if the
proxy config drifts, the app still emits them.

HSTS is only sent over TLS (or when explicitly forced), because sending
`Strict-Transport-Security` over plain HTTP is meaningless and pinning
localhost to HTTPS during development breaks the dev server.
"""
from __future__ import annotations

import logging
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.config import settings

logger = logging.getLogger(__name__)


def _origin_of(url: str) -> str:
    """``https://bucket.s3.example.com/x/y`` -> ``https://bucket.s3.example.com``."""
    if not url:
        return ""
    parts = urlsplit(url if "//" in url else f"https://{url}")
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}"


def build_csp(cfg=None) -> str:
    """Content-Security-Policy, derived from the storage configuration.

    ``img-src`` must list wherever product images are actually served from —
    the configured S3/CDN base URL — instead of a host name copied from a
    deployment guide (IR-005). ``https://images.unsplash.com`` stays because the
    committed demo catalog references it; it is a documented demo dependency,
    not a production requirement.

    Stage 2 (T-2.4, B-11): this function is the SINGLE SOURCE OF TRUTH for the
    CSP. The Caddyfile carries a byte-identical copy for defence in depth;
    ``tests/test_csp_alignment.py`` fails whenever the two drift, and
    ``scripts/print_csp.py`` regenerates the proxy copy after a config change.
    Image origins come from, in order: ``S3_PUBLIC_BASE_URL``, ``S3_ENDPOINT``
    (plus its ``https://*.host`` variant for virtual-hosted buckets),
    ``IMAGE_CDN_BASE_URL`` and ``IMAGE_EXTRA_ORIGINS``.
    """
    cfg = cfg or settings
    img_sources = ["'self'", "data:", "blob:", "https://images.unsplash.com"]

    def _add(origin: str) -> None:
        if origin and origin not in img_sources:
            img_sources.append(origin)

    _add(_origin_of(cfg.S3_PUBLIC_BASE_URL))
    endpoint_origin = _origin_of(cfg.S3_ENDPOINT)
    _add(endpoint_origin)
    if endpoint_origin:
        # Virtual-hosted buckets resolve as <bucket>.<endpoint-host>; the
        # Caddyfile always allowed that pattern, the app copy did not (B-11).
        scheme, _, host = endpoint_origin.partition("://")
        _add(f"{scheme}://*.{host}")
    _add(_origin_of(getattr(cfg, "IMAGE_CDN_BASE_URL", "")))
    for extra in (getattr(cfg, "IMAGE_EXTRA_ORIGINS", "") or "").split(","):
        _add(_origin_of(extra.strip()))

    directives = [
        "default-src 'self'",
        # No 'unsafe-inline': the SPA bundle has no inline script (T-41).
        "script-src 'self'",
        # Tailwind/emotion style injection still needs inline styles. Inline
        # style is a far weaker primitive than inline script and removing it
        # would break the design system, so it is an accepted, documented gap.
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' data: https://fonts.gstatic.com",
        f"img-src {' '.join(img_sources)}",
        "connect-src 'self' https://generativelanguage.googleapis.com",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
        "worker-src 'self' blob:",
        "manifest-src 'self'",
    ]
    if cfg.is_production:
        directives.append("upgrade-insecure-requests")
    return "; ".join(directives)


CSP = build_csp()

STATIC_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), interest-cohort=(), "
        "payment=(), usb=(), magnetometer=(), accelerometer=()"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
    "X-Permitted-Cross-Domain-Policies": "none",
}

HSTS = "max-age=63072000; includeSubDomains; preload"


def _is_tls(request: Request) -> bool:
    return request.url.scheme == "https" or (
        request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"
    )


def apply_security_headers(
    request: Request, response: Response, *, force_hsts: bool | None = None
) -> Response:
    """Stamp the headers onto ``response``. Safe to call more than once.

    Exposed as a function (not only as middleware) so exception handlers can
    guarantee the headers on responses that never traverse the middleware
    stack.
    """
    for header, value in STATIC_HEADERS.items():
        response.headers.setdefault(header, value)

    if (settings.is_production if force_hsts is None else force_hsts) or _is_tls(request):
        response.headers.setdefault("Strict-Transport-Security", HSTS)

    # Do not advertise the server stack (fingerprinting aid).
    response.headers["Server"] = settings.APP_NAME

    # Never let a browser or shared cache retain authenticated API payloads.
    # `Vary` matters as much as `no-store`: without it an intermediary keyed on
    # the URL alone could serve one tenant's cached response to another.
    if request.url.path.startswith(settings.API_V1_PREFIX):
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Pragma", "no-cache")
        existing_vary = response.headers.get("Vary")
        wanted = "Cookie, Authorization, Origin"
        response.headers["Vary"] = f"{existing_vary}, {wanted}" if existing_vary else wanted
    return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach OWASP-recommended security headers to every response."""

    def __init__(self, app: ASGIApp, force_hsts: bool | None = None) -> None:
        super().__init__(app)
        # In production we always want HSTS (TLS is terminated at Caddy, so the
        # request reaching us may look like plain HTTP).
        self.force_hsts = (
            settings.is_production if force_hsts is None else force_hsts
        )

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            # T-39 / probe H-01. Owning the failure path here (rather than
            # letting the exception reach ServerErrorMiddleware, which sits
            # *outside* this middleware) is what guarantees the hardened
            # headers and a JSON envelope on a 500 — the exact response class
            # an attacker sees while fuzzing. The traceback goes to the log,
            # never to the client (T-24).
            logger.exception("unhandled error while serving %s", request.url.path)
            response = JSONResponse(
                status_code=500,
                content={"success": False, "data": None,
                         "error": "Internal server error"},
            )
        return apply_security_headers(request, response, force_hsts=self.force_hsts)
