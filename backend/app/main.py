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
    moodboards,
    products,
    projects,
    quiz,
    subscriptions,
    users,
)
from app.core.config import settings

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Smart Interior Decor Recommendation Platform — living room MVP.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException):
    """Consistent envelope for errors: {success: false, error: ...}."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "error": str(exc.detail)},
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
