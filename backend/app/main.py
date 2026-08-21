"""Smart Interior Decor Recommendation Platform — FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import (
    admin,
    auth,
    feedback,
    health as health_routes,
    moodboards,
    products,
    projects,
    quiz,
    subscriptions,
    users,
)
from app.core.config import Settings, settings
from app.core.json_response import ORJSONResponse
from app.core.log_redaction import install_log_redaction
from app.core.observability import (
    MetricsMiddleware,
    RequestIDMiddleware,
    setup_structured_logging,
)
from app.core.security_headers import SecurityHeadersMiddleware, apply_security_headers

logging.basicConfig(level=logging.INFO)

# Stage 03 (T-38): install the redacting filter before anything can log. Every
# handler on the root logger — including uvicorn's — gets it.
install_log_redaction()
# Stage 07: configure level/format and correlate application logs. This is
# deliberately after the Stage 03 redaction factory so both controls compose.
setup_structured_logging()

logger = logging.getLogger(__name__)

# V2 (OWASP A02/A04): refuse to start production with weak secrets, no Redis,
# or insecure cookies. Stage 03 extends this to demo-account seeding, a
# non-https frontend origin, a missing Fernet key, local media storage and a
# non-HMAC JWT algorithm. No-op outside production apart from the algorithm
# check, which applies everywhere.
settings.validate_runtime()


def build_cors_origins(cfg: Settings | None = None) -> list[str]:
    """Origins allowed to send credentialed cross-origin requests.

    Stage 03 (T-40): the v2 list was ``[FRONTEND_ORIGIN, "http://localhost:5173",
    "http://localhost:4173"]`` **in every environment**, combined with
    ``allow_credentials=True``. In production that means any process able to
    serve content on a developer's loopback port — a malicious npm postinstall
    script, a compromised local tool, another tenant on a shared workstation —
    could read authenticated API responses cross-origin. Development keeps the
    convenience; production gets exactly one origin.
    """
    cfg = cfg or settings
    origins = [cfg.FRONTEND_ORIGIN]
    if not cfg.is_production:
        origins += ["http://localhost:5173", "http://localhost:4173"]
    # dict.fromkeys: de-duplicate while preserving order.
    return list(dict.fromkeys(o for o in origins if o))


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Startup fail-safes that need a database connection.

    Stage 03 (T-01): configuration alone cannot prove a production database is
    free of predictable logins — the rows may predate this fix or arrive with a
    restored staging dump. Refusing to serve is the safe direction: a process
    that will not start is a five-minute incident, an internet-facing platform
    with a published admin password is not.
    """
    if settings.is_production:
        from app.core.demo_seed import assert_no_demo_accounts_in_production
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            assert_no_demo_accounts_in_production(db)
        finally:
            db.close()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Smart Interior Decor Recommendation Platform — living room MVP.",
    # Perf (V2 Phase 2): orjson serialises the recommendation envelope — a
    # deeply nested dict of ~40 products with float score breakdowns — several
    # times faster than the stdlib encoder, and it emits floats without the
    # repr round-trip. /recommend is the heaviest JSON payload in the API.
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    # Stage 03: interactive docs are useful in development and are an attack
    # surface map in production.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# Order matters: middleware added last runs first on the response path, so
# SecurityHeadersMiddleware is added after CORS to stamp every response
# (including CORS preflights and error envelopes).
app.add_middleware(
    CORSMiddleware,
    allow_origins=build_cors_origins(),
    allow_credentials=True,
    # V2 (A05): narrowed from "*" to exactly what the SPA uses.
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)
# Stage 07: metrics is inside request-ID middleware so all observations carry
# the same correlation context. RequestID is added last and therefore runs
# outermost on the Starlette middleware stack.
app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestIDMiddleware)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Consistent envelope for errors: {success: false, error: ...}.

    V2 fix: the v1 handler dropped ``exc.headers``, which silently swallowed
    the ``Retry-After`` header on every 429 (and ``WWW-Authenticate`` on 401).
    """
    headers = dict(getattr(exc, "headers", None) or {})
    response = ORJSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "error": str(exc.detail)},
        headers=headers,
    )
    # Stage 03 (T-39): stamp here too. An HTTPException raised inside a
    # dependency is handled by ExceptionMiddleware, which sits *inside* the
    # middleware stack, so the response does pass back through
    # SecurityHeadersMiddleware — but making it explicit costs nothing and
    # keeps the guarantee true if the stack is ever reordered.
    return apply_security_headers(request, response)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """422 envelope that names the offending field without echoing its value.

    Stage 03 (T-24/H-03): the v2 handler returned ``str(exc.errors()[:3])``,
    and pydantic's error dicts carry an ``input`` key holding the submitted
    value verbatim. That reflected attacker- (or victim-) supplied content
    straight back into the response body: a self-XSS vector against any client
    that renders the error as HTML, a way to confirm what a server-side proxy
    rewrote, and a needless disclosure of whatever was in the failing field
    (including passwords on a malformed registration).
    """
    details = []
    for err in exc.errors()[:5]:
        location = ".".join(str(part) for part in err.get("loc", ()) if part != "body")
        details.append({
            "field": location or "body",
            "type": err.get("type", "value_error"),
            "message": str(err.get("msg", "invalid value"))[:200],
        })
    response = ORJSONResponse(
        status_code=422,
        content={"success": False, "data": None,
                 "error": "Validation failed", "details": details},
    )
    return apply_security_headers(request, response)


@app.get("/api/v1/health", tags=["health"])
def health():
    return {"success": True, "data": {"status": "ok", "env": settings.APP_ENV}, "error": None}


for router in (
    auth.router,
    users.router,
    quiz.router,
    feedback.router,
    products.router,
    moodboards.router,
    projects.router,
    subscriptions.router,
    admin.router,
):
    app.include_router(router, prefix=settings.API_V1_PREFIX)

# Readiness is under the versioned API prefix; metrics follows the Prometheus
# convention and remains at the bare /metrics path.
app.include_router(health_routes.router, prefix=settings.API_V1_PREFIX)
app.include_router(health_routes.metrics_router)

# Serve local storage in dev (S3 serves media in production).
# Stage 03: `validate_runtime()` refuses STORAGE_BACKEND=local in production, so
# this same-origin media mount can only exist in dev/test. Uploads are
# additionally magic-byte sniffed and re-encoded (app.core.uploads), so nothing
# that a browser would execute can land here in the first place.
if settings.STORAGE_BACKEND == "local":
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    media_dir = Path(settings.LOCAL_STORAGE_DIR)
    media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")
