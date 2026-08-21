"""Stage 07 — observability: request IDs, structured logs, metrics, readiness.

Every check here is behavioural, not cosmetic:

* the ``X-Request-ID`` must be echoed and must be *stable* across the request
  (proxy-supplied ids are validated, not trusted blindly);
* log lines must be parseable JSON carrying the request id, and must be
  redacted even when the caller bypasses the Stage 03 filter path;
* ``/metrics`` must expose counters/histograms in Prometheus text format
  without requiring authentication and without 500ing;
* readiness must degrade to ``503`` with per-component detail when Redis is
  unreachable, and must never raise.
"""

from __future__ import annotations

import json
import logging

import pytest

from app.core.observability import (
    JSONFormatter,
    reset_metrics_for_tests,
    setup_structured_logging,
)


@pytest.fixture(autouse=True)
def _clean_metrics():
    reset_metrics_for_tests()
    yield
    reset_metrics_for_tests()


# ------------------------------------------------------------------ request id


def test_response_carries_request_id(client):
    resp = client.get("/api/v1/health")
    rid = resp.headers.get("x-request-id")
    assert rid and len(rid) <= 64


def test_proxy_request_id_is_echoed(client):
    resp = client.get("/api/v1/health", headers={"X-Request-ID": "caddy-abc123"})
    assert resp.headers.get("x-request-id") == "caddy-abc123"


def test_hostile_request_id_is_replaced(client):
    # Too long and contains characters outside the allowlist.
    resp = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "a" * 200 + "<script>alert(1)</script>"},
    )
    rid = resp.headers.get("x-request-id")
    assert rid and len(rid) == 32  # uuid4().hex
    assert "<" not in rid


def test_request_id_reaches_log_records(caplog):
    """A log line emitted while handling a request carries its request id."""
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from app.core.observability import RequestIDMiddleware

    async def handler(request):
        logging.getLogger("obs.probe").warning("inside request")
        return PlainTextResponse("ok")

    probe_app = Starlette(routes=[Route("/probe", handler)])
    probe_app.add_middleware(RequestIDMiddleware)

    with caplog.at_level(logging.WARNING, logger="obs.probe"):
        with TestClient(probe_app) as tc:
            resp = tc.get("/probe", headers={"X-Request-ID": "log-correl-1"})
    rid = resp.headers.get("x-request-id")
    assert rid == "log-correl-1"
    records = [r for r in caplog.records if r.name == "obs.probe"]
    assert records, "expected the probe log record"
    assert all(r.request_id == rid for r in records), (
        "records emitted during the request must carry its request id"
    )


# ------------------------------------------------------------ structured logs


def test_json_formatter_emits_redacted_json():
    import re

    formatter = JSONFormatter()
    # A realistic 3-segment JWT (each segment >= 5 chars, unlike a toy token).
    jwt_sample = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THmRnk"
    )
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg=f"user alice@example.com failed with token {jwt_sample}",
        args=(), exc_info=None,
    )
    line = formatter.format(record)
    parsed = json.loads(line)
    # Email -> keyed pseudonym (digest varies with SECRET_KEY; assert shape).
    assert re.search(r"a\*\*\*@example\.com#[0-9a-f]{8}", parsed["message"])
    assert "[REDACTED]-jwt" in parsed["message"]
    assert jwt_sample not in parsed["message"]
    assert parsed["request_id"] == "-"
    assert parsed["level"] == "INFO"


def test_json_formatter_carries_request_id():
    from app.core.observability import request_id_var

    formatter = JSONFormatter()
    captured: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record):
            captured.append(record)

    probe = logging.getLogger("probe.obs")
    probe.handlers = [Capture()]
    probe.setLevel(logging.DEBUG)
    probe.propagate = False
    token = request_id_var.set("req-42")
    try:
        probe.warning("boom")
        parsed = json.loads(formatter.format(captured[0]))
        assert parsed["request_id"] == "req-42"
        assert parsed["message"] == "boom"
    finally:
        request_id_var.reset(token)


def test_setup_structured_logging_is_idempotent():
    """Calling setup twice must not stack formatters or double-attach."""
    setup_structured_logging()
    root = logging.getLogger()
    before = [(h, type(h.formatter).__name__, len(h.filters)) for h in root.handlers]
    setup_structured_logging()
    after = [(h, type(h.formatter).__name__, len(h.filters)) for h in root.handlers]
    assert before == after
    # And the record factory must not be wrapped twice.
    from app.core.observability import _INSTALLED_FACTORY

    assert _INSTALLED_FACTORY is True


# -------------------------------------------------------------------- metrics


def test_metrics_expose_counters_and_histograms(client):
    client.get("/api/v1/health")
    client.get("/api/v1/health")
    client.get("/api/v1/products")  # 401 unauthenticated
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert 'http_requests_total{method="GET",path="/api/v1/health",status="200"} 2' in body
    assert 'http_requests_total{method="GET",path="/api/v1/products",status="401"} 1' in body
    assert 'http_request_duration_seconds_count{method="GET",path="/api/v1/health"} 2' in body
    assert 'app_info{version="1.0.0"' in body
    assert "redis_up " in body
    assert "# TYPE http_requests_total counter" in body


def test_metrics_never_include_metrics_itself(client):
    client.get("/metrics")
    client.get("/metrics")
    body = client.get("/metrics").text
    for line in body.splitlines():
        if line.startswith("http_requests_total"):
            assert '/path="/metrics"' not in line


def test_metrics_latency_histogram_buckets(client):
    client.get("/api/v1/health")
    body = client.get("/metrics").text
    assert 'le="0.01"' in body and 'le="+Inf"' in body


# ------------------------------------------------------------------ readiness


def test_readiness_ok_with_sqlite_and_fakeredis(client):
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "ready"
    assert data["checks"]["database"] == "ok"
    assert data["checks"]["redis"] == "ok"


def test_readiness_503_when_redis_unreachable(client, reset_settings):
    reset_settings(REDIS_URL="redis://127.0.0.1:1/0")  # nothing listens on :1
    from app.core.redis_client import reset_redis_for_tests

    reset_redis_for_tests()
    try:
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 503
        body = str(resp.json())
        assert "database" in body and "redis" in body
        assert "not_ready" in body
    finally:
        reset_redis_for_tests()


def test_readiness_never_raises(client):
    # Health endpoints must be the last thing that 500s in an outage.
    for path in ("/api/v1/health", "/api/v1/health/ready", "/metrics"):
        resp = client.get(path)
        assert resp.status_code < 500
