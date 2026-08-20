"""Smart Interior Decor Recommendation Platform — FastAPI application."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import (
    admin,
    auth,
    feedback,
    moodboards,
    products,
    projects,
    quiz,
    subscriptions,
    users,
)
from app.core.config import settings
from app.core.json_response import ORJSONResponse
from app.core.security_headers import SecurityHeadersMiddleware

logging.basicConfig(level=logging.INFO)

# V2 (OWASP A02/A04): refuse to start production with weak secrets, no Redis,
# or insecure cookies. No-op outside production.
settings.validate_runtime()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Smart Interior Decor Recommendation Platform — living room MVP.",
    # Perf (V2 Phase 2): orjson serialises the recommendation envelope — a
    # deeply nested dict of ~40 products with float score breakdowns — several
    # times faster than the stdlib encoder, and it emits floats without the
    # repr round-trip. /recommend is the heaviest JSON payload in the API.
    default_response_class=ORJSONResponse,
)

# Order matters: middleware added last runs first on the response path, so
# SecurityHeadersMiddleware is added after CORS to stamp every response
# (including CORS preflights and error envelopes).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    # V2 (A05): narrowed from "*" to exactly what the SPA uses.
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException):
    """Consistent envelope for errors: {success: false, error: ...}.

    V2 fix: the v1 handler dropped ``exc.headers``, which silently swallowed
    the ``Retry-After`` header on every 429 (and ``WWW-Authenticate`` on 401).
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "error": str(exc.detail)},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"success": False, "data": None, "error": str(exc.errors()[:3])},
    )


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

# Serve local storage in dev (S3 serves media in production)
if settings.STORAGE_BACKEND == "local":
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    media_dir = Path(settings.LOCAL_STORAGE_DIR)
    media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")
