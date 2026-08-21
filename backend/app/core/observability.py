"""Observability: request IDs, structured JSON logs and Prometheus metrics.

Stage 07 (Master Prompt 07 — Infrastructure / Observability). All changes
here are additive and carry no business logic:

* :class:`RequestIDMiddleware` — accepts a validated ``X-Request-ID`` from the
  proxy (Caddy) or generates one, echoes it on the response, and publishes it
  to a ``contextvars`` slot so every log line emitted while handling the
  request carries the same id. One id per request across nginx → Caddy →
  uvicorn workers → Redis/Postgres round-trips is what makes distributed
  debugging possible at all.
* :class:`JSONFormatter` + :func:`setup_structured_logging` — machine-parseable
  one-line JSON logs instead of the default text format. Every message passes
  through ``app.core.log_redaction.redact`` **again** at the formatter, so a
  future logger that bypasses the Stage 03 filter still cannot leak a token or
  an email into the JSON stream. JSON is the default in production; dev/test
  keep the readable text format unless ``LOG_FORMAT=json`` is set explicitly.
* :class:`MetricsMiddleware` + :func:`render_metrics` — dependency-free
  Prometheus text exposition: request counters, a latency histogram and an
  in-flight gauge, plus a lazy ``redis_up`` probe and ``app_info`` on scrape.
  Rate-limit counters, AI cost and payment-state metrics need route-level
  instrumentation and are tracked in ``integration-request.md`` (IR-INF-006).

Nothing here touches responses except adding the ``X-Request-ID`` header and
the additive ``/metrics`` endpoint; the full test suite must stay green.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from contextvars import ContextVar
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.log_redaction import redact

logger = logging.getLogger(__name__)

#: Request id for the current request, readable by any logger in this process.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

#: RFC-safe header charset, length-bounded. Anything else is replaced by a
#: freshly generated id — a proxy header is a hint, not a trust boundary.
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")

MAX_ID_LENGTH = 64

# ---------------------------------------------------------------------------
# Request IDs
# ---------------------------------------------------------------------------

_INSTALLED_FACTORY = False


def install_request_id_factory() -> None:
    """Stamp ``record.request_id`` at record-creation time, like Stage 03's
    redaction factory: the only hook that covers handlers attached later
    (APM sidecars, pytest's caplog, a collector added at runtime). Idempotent.
    """
    global _INSTALLED_FACTORY
    if _INSTALLED_FACTORY:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        record.request_id = request_id_var.get() or "-"
        return record

    logging.setLogRecordFactory(factory)
    _INSTALLED_FACTORY = True


def _generate_request_id() -> str:
    import uuid

    return uuid.uuid4().hex


def _validated_request_id(header: str | None) -> str:
    if header and _REQUEST_ID_RE.match(header):
        return header
    return _generate_request_id()


access_logger = logging.getLogger("app.access")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Correlate every log line and every response with one request id."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _validated_request_id(request.headers.get("x-request-id"))
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            # Keep the response observable even on an unhandled error: the
            # request id must still reach the logs and the response header.
            duration_ms = (time.perf_counter() - started) * 1000.0
            access_logger.exception(
                "http_request_unhandled",
                extra={
                    "event": "http_request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "duration_ms": f"{duration_ms:.1f}",
                },
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
        # Rich access line, emitted INSIDE the request context so the record
        # factory stamps the request id (uvicorn's own access log runs outside
        # the request context and cannot correlate — it is silenced below).
        access_logger.info(
            "http_request",
            extra={
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": f"{duration_ms:.1f}",
            },
        )
        request_id_var.reset(token)
        response.headers.setdefault("X-Request-ID", request_id)
        return response


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------


class JSONFormatter(logging.Formatter):
    """One-line JSON per record, redacted at the formatter boundary.

    ``record.args`` are rendered eagerly so the redactor sees the final text
    (the Stage 03 filter already does this, but a formatter that redacts again
    protects loggers registered after that filter was installed).
    """

    def format(self, record: logging.LogRecord) -> str:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            message = str(record.msg)
        entry: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(message),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        # Extra fields (e.g. {"event": "login_failed", "user": ...}) are
        # redacted individually; keys are never redacted.
        for key in ("event", "path", "method", "status", "duration_ms",
                    "rows_purged", "retention_days", "worker"):
            value = getattr(record, key, None)
            if value is not None:
                entry[key] = redact(str(value)) if isinstance(value, str) else value
        return json.dumps(entry, ensure_ascii=False, default=str)


_JSON_FORMATTERS_APPLIED = False


def setup_structured_logging() -> None:
    """Configure root logging: level, optional JSON formatter, request-id stamp.

    Idempotent and safe to call more than once (uvicorn imports the app once
    per worker; ``--reload`` re-imports it many times). The request-id factory
    is installed exactly once; JSON formatters are applied to whatever root
    handlers exist at first call and never re-applied, so pytest's own
    log-capture handler keeps its text formatter for ``caplog`` assertions.
    """
    global _JSON_FORMATTERS_APPLIED
    install_request_id_factory()

    level = getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO)
    use_json = str(settings.LOG_FORMAT).lower() == "json"

    # Take over uvicorn's own loggers so their records flow through the root
    # handlers (and therefore the redaction + JSON formatting + request id).
    # uvicorn.access is silenced: its records are created outside the request
    # context (no request_id) — RequestIDMiddleware emits a correlated
    # `app.access` line instead.
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
        lg.setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(logging.CRITICAL)

    root = logging.getLogger()
    root.setLevel(level)
    if use_json and not _JSON_FORMATTERS_APPLIED:
        for handler in list(root.handlers):
            if not isinstance(handler.formatter, JSONFormatter):
                handler.setFormatter(JSONFormatter())
        _JSON_FORMATTERS_APPLIED = True


# ---------------------------------------------------------------------------
# Metrics (Prometheus text exposition, stdlib only)
# ---------------------------------------------------------------------------

_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_LOCK = threading.Lock()
# (method, path_label, status) -> count
_COUNTER: dict[tuple[str, str, int], int] = {}
# (method, path_label) -> [count, sum, bucket counts...]
_HISTOGRAM: dict[tuple[str, str], list[float]] = {}
_INFLIGHT: int = 0
# Keep label cardinality bounded: bucket to /api/v1/<resource> or top-level.
_SKIP_PATHS = {"/metrics"}


def _path_label(path: str) -> str:
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "/"
    if parts[0] == "api" and len(parts) >= 3:
        return f"/api/{parts[1]}/{parts[2]}"
    return f"/{parts[0]}"


def record_request(method: str, path: str, status: int, duration_s: float) -> None:
    if path in _SKIP_PATHS:
        return
    label = _path_label(path)
    with _LOCK:
        key = (method, label, status)
        _COUNTER[key] = _COUNTER.get(key, 0) + 1
        hist = _HISTOGRAM.setdefault((method, label), [0.0, 0.0] + [0.0] * len(_BUCKETS))
        hist[0] += 1
        hist[1] += duration_s
        for i, bound in enumerate(_BUCKETS):
            if duration_s <= bound:
                hist[2 + i] += 1


def reset_metrics_for_tests() -> None:
    with _LOCK:
        _COUNTER.clear()
        _HISTOGRAM.clear()
        global _INFLIGHT
        _INFLIGHT = 0


class MetricsMiddleware(BaseHTTPMiddleware):
    """Count and time every request; never raises (metrics must not 500)."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        global _INFLIGHT
        start = time.perf_counter()
        status = 500  # unhandled exceptions are counted, not lost
        with _LOCK:
            _INFLIGHT += 1
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            duration = time.perf_counter() - start
            with _LOCK:
                _INFLIGHT -= 1
            record_request(request.method, request.url.path, status, duration)
        return response


def render_metrics() -> str:
    """Prometheus text exposition. Safe for concurrent scrapes."""
    lines = [
        "# HELP app_info Static application metadata.",
        "# TYPE app_info gauge",
        f'app_info{{version="1.0.0",env="{settings.APP_ENV}"}} 1',
        "# HELP http_requests_total Requests by method, resource and status.",
        "# TYPE http_requests_total counter",
    ]
    with _LOCK:
        for (method, label, status), count in sorted(_COUNTER.items()):
            lines.append(
                f'http_requests_total{{method="{method}",path="{label}",'
                f'status="{status}"}} {count}'
            )
        lines += [
            "# HELP http_request_duration_seconds Request latency histogram.",
            "# TYPE http_request_duration_seconds histogram",
        ]
        for (method, label), hist in sorted(_HISTOGRAM.items()):
            cumulative = 0.0
            for i, bound in enumerate(_BUCKETS):
                cumulative += hist[2 + i]
                lines.append(
                    f'http_request_duration_seconds_bucket{{method="{method}",'
                    f'path="{label}",le="{bound}"}} {int(cumulative)}'
                )
            lines.append(
                f'http_request_duration_seconds_bucket{{method="{method}",'
                f'path="{label}",le="+Inf"}} {int(hist[0])}'
            )
            lines.append(
                f'http_request_duration_seconds_sum{{method="{method}",'
                f'path="{label}"}} {hist[1]:.6f}'
            )
            lines.append(
                f'http_request_duration_seconds_count{{method="{method}",'
                f'path="{label}"}} {int(hist[0])}'
            )
        lines.append("# HELP http_requests_inflight In-flight requests.")
        lines.append("# TYPE http_requests_inflight gauge")
        lines.append(f"http_requests_inflight {_INFLIGHT}")

    # Lazy, time-boxed dependency probe: Redis reachability at scrape time.
    redis_up = 0
    try:
        from app.core.redis_client import ping

        redis_up = 1 if ping() else 0
    except Exception:
        redis_up = 0
    lines.append("# HELP redis_up Whether the shared Redis answered PING.")
    lines.append("# TYPE redis_up gauge")
    lines.append(f"redis_up {redis_up}")
    return "\n".join(lines) + "\n"
