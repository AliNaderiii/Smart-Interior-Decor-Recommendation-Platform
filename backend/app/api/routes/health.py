"""Health, readiness and metrics endpoints (Stage 07 — observability).

* ``GET /api/v1/health`` — liveness (existing, defined in ``app/main.py``).
* ``GET /api/v1/health/ready`` — **readiness**: verifies the database answers
  ``SELECT 1`` and the shared Redis answers ``PING``. Returns ``200`` only
  when every dependency the request path needs is reachable, ``503`` with a
  per-component breakdown otherwise. A load balancer / orchestrator should
  send traffic to this endpoint — never to liveness — and the docker-compose
  backend healthcheck uses it.
* ``GET /metrics`` — Prometheus text exposition (see
  ``app.core.observability``). Additive and unauthenticated on purpose:
  Prometheus scrapes do not carry user credentials; the endpoint exposes no
  PII, only counters. Restrict it at the proxy/network layer if the metrics
  collector is not on the same network (see docs/DEPLOYMENT.md §observability).
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.observability import render_metrics
from app.db.session import engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

#: Bare /metrics (Prometheus convention) — included WITHOUT the /api/v1
#: prefix in app/main.py; the Caddyfile routes it to the backend directly.
metrics_router = APIRouter(tags=["metrics"])


def _check_database() -> tuple[bool, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - readiness must never raise
        logger.warning("readiness: database check failed: %s", exc)
        return False, f"unreachable: {type(exc).__name__}"


def _check_redis() -> tuple[bool, str]:
    try:
        from app.core.redis_client import ping

        if ping():
            return True, "ok"
        return False, "unreachable"
    except Exception as exc:  # noqa: BLE001
        logger.warning("readiness: redis check failed: %s", exc)
        return False, f"unreachable: {type(exc).__name__}"


@router.get("/health/ready")
def readiness() -> dict:
    """200 when DB and Redis both answer; 503 with details otherwise."""
    db_ok, db_state = _check_database()
    redis_ok, redis_state = _check_redis()
    checks = {
        "database": db_state,
        "redis": redis_state,
        "env": settings.APP_ENV,
    }
    if db_ok and redis_ok:
        return {
            "success": True,
            "data": {"status": "ready", "checks": checks},
            "error": None,
        }
    from fastapi import HTTPException

    raise HTTPException(
        status_code=503,
        detail={
            "status": "not_ready",
            "checks": checks,
        },
    )


@metrics_router.get("/metrics", include_in_schema=False)
def metrics() -> PlainTextResponse:
    """Prometheus text exposition (stdlib counters + lazy redis probe)."""
    if not settings.METRICS_ENABLED:
        return PlainTextResponse("metrics disabled\n", status_code=404)
    started = time.perf_counter()
    body = render_metrics()
    # Cheap self-metric so the collector can see scrape cost.
    body += f'# scrape_duration_seconds {time.perf_counter() - started:.6f}\n'
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4")
