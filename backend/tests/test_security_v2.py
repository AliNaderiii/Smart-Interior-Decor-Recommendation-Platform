"""Phase 1 security regression tests (V2 strict mode).

Every test here pins a specific FAIL recorded in `docs/SECURITY_AUDIT_V2.md`
so the vulnerability cannot silently return.
"""
from __future__ import annotations

import pytest

from app.core import brute_force
from app.core.config import settings
from app.core.redis_client import get_redis
from app.schemas.sanitize import strip_html


@pytest.fixture(autouse=True)
def _clear_bf():
    get_redis().flushall()
    yield


# --------------------------------------------------------------- A05 headers

REQUIRED_HEADERS = {
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
}


def test_security_headers_present_on_every_response(client):
    """A05: Phase 0B found 0 of 6 headers present."""
    resp = client.get("/api/v1/health")
    lowered = {k.lower() for k in resp.headers}
    missing = REQUIRED_HEADERS - lowered
    assert not missing, f"missing security headers: {sorted(missing)}"


def test_security_headers_present_on_error_responses(client):
    """Error envelopes must be hardened too, not just 200s."""
    resp = client.get("/api/v1/moodboards")  # 401, unauthenticated
    assert resp.status_code == 401
    lowered = {k.lower() for k in resp.headers}
    assert REQUIRED_HEADERS - lowered == set()


def test_clickjacking_and_sniffing_values(client):
    resp = client.get("/api/v1/health")
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in resp.headers["content-security-policy"]


def test_hsts_sent_when_request_is_tls_terminated(client):
    resp = client.get("/api/v1/health", headers={"X-Forwarded-Proto": "https"})
    assert "max-age=63072000" in resp.headers["strict-transport-security"]


def test_no_server_stack_disclosure(client):
    resp = client.get("/api/v1/health")
    assert "uvicorn" not in resp.headers.get("server", "").lower()


def test_api_responses_are_not_cacheable(client):
    resp = client.get("/api/v1/health")
    assert resp.headers.get("cache-control") == "no-store"


# ----------------------------------------------------------- A07 brute force


def test_brute_force_blocks_after_five_failures(client):
    """A07: Phase 0B ran 8 wrong passwords and got 401 every time."""
    email = "brute-target@smartdecor.dev"
    codes = [
        client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        ).status_code
        for _ in range(7)
    ]
    assert codes[:4] == [401, 401, 401, 401], codes
    assert codes[4] == 429, f"5th failure must be blocked, got {codes}"
    assert all(c == 429 for c in codes[4:]), codes


def test_brute_force_429_carries_retry_after_header(client):
    """The v1 exception handler dropped exc.headers, swallowing Retry-After."""
    email = "brute-retry@smartdecor.dev"
    resp = None
    for _ in range(6):
        resp = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "nope"}
        )
    assert resp.status_code == 429
    assert int(resp.headers["retry-after"]) > 0


def test_lockout_does_not_leak_account_existence(client):
    """Blocking must apply to unknown emails too, or it becomes an oracle."""
    for _ in range(6):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "no-such-user@smartdecor.dev", "password": "x"},
        )
    assert resp.status_code == 429


def test_lockout_is_scoped_and_cannot_dos_other_accounts(client, demo_user):
    """One attacker must not lock everyone else out from the same IP."""
    for _ in range(6):
        client.post(
            "/api/v1/auth/login",
            json={"email": "victim-dos@smartdecor.dev", "password": "wrong"},
        )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": demo_user["email"], "password": demo_user["password"]},
    )
    assert resp.status_code == 200, "unrelated account was collaterally locked out"


def test_successful_login_clears_failure_counter(client, demo_user):
    for _ in range(3):
        client.post(
            "/api/v1/auth/login",
            json={"email": demo_user["email"], "password": "wrong"},
        )
    assert brute_force.remaining_attempts("testclient", demo_user["email"]) < 5
    client.post(
        "/api/v1/auth/login",
        json={"email": demo_user["email"], "password": demo_user["password"]},
    )
    assert brute_force.remaining_attempts("testclient", demo_user["email"]) == 5


# --------------------------------------------------------- A04 input validation


def test_oversize_title_returns_422_not_500(client, bearer_headers):
    """A04: Phase 0B got a 500 (StringDataRightTruncation) from a 5000-char title."""
    resp = client.post(
        "/api/v1/moodboards", json={"title": "A" * 5000}, headers=bearer_headers
    )
    assert resp.status_code == 422, resp.text


def test_unknown_fields_are_rejected(client, bearer_headers):
    """A04: mass-assignment surface — Phase 0B returned 201."""
    resp = client.post(
        "/api/v1/moodboards",
        json={"title": "ok", "is_admin": True, "user_id": "1001"},
        headers=bearer_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "extra_forbidden" in resp.text


# ------------------------------------------------------------------- A03 XSS


@pytest.mark.parametrize(
    "payload,expected",
    [
        ("<img src=x onerror=alert(1)><script>alert(2)</script>Living Room", "Living Room"),
        ("&lt;script&gt;alert(1)&lt;/script&gt;Hi", "Hi"),
        ("<style>body{}</style>Nordic", "Nordic"),
        ("<svg onload=alert(1)></svg>Loft", "Loft"),
        ("Perfectly Normal Title 2026", "Perfectly Normal Title 2026"),
    ],
)
def test_html_is_stripped(payload, expected):
    assert strip_html(payload) == expected


def test_stored_xss_is_sanitised_end_to_end(client, bearer_headers):
    """A03: Phase 0B persisted the payload verbatim."""
    resp = client.post(
        "/api/v1/moodboards",
        json={"title": "<script>alert(1)</script>My Board"},
        headers=bearer_headers,
    )
    assert resp.status_code == 201, resp.text
    title = resp.json()["data"]["title"]
    assert "<script>" not in title
    assert "alert(1)" not in title
    assert title == "My Board"


# ------------------------------------------------------------ A02 cookie auth


@pytest.mark.skipif(not settings.USE_COOKIE_AUTH, reason="cookie auth disabled")
def test_login_sets_httponly_cookies(client, demo_user):
    """A02: Phase 0B found no Set-Cookie at all."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": demo_user["email"], "password": demo_user["password"]},
    )
    assert resp.status_code == 200
    raw = resp.headers.get_list("set-cookie")
    access = next(c for c in raw if c.startswith("access_token="))
    refresh = next(c for c in raw if c.startswith("refresh_token="))
    for cookie in (access, refresh):
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie.replace("samesite", "SameSite")
    # CSRF cookie must be readable by JS (double-submit pattern).
    csrf = next(c for c in raw if c.startswith("csrf_token="))
    assert "HttpOnly" not in csrf


@pytest.mark.skipif(not settings.USE_COOKIE_AUTH, reason="cookie auth disabled")
def test_cookie_auth_state_change_requires_csrf_token(client, demo_user):
    """Cookie-authenticated POST without the echoed CSRF header must fail."""
    login = client.post(
        "/api/v1/auth/login",
        json={"email": demo_user["email"], "password": demo_user["password"]},
    )
    csrf = login.json()["data"]["csrf_token"]

    # No X-CSRF-Token -> rejected
    blocked = client.post("/api/v1/moodboards", json={"title": "CSRF attempt"})
    assert blocked.status_code == 403

    # With the token -> allowed
    allowed = client.post(
        "/api/v1/moodboards",
        json={"title": "Legit board"},
        headers={"X-CSRF-Token": csrf},
    )
    assert allowed.status_code == 201


# ---------------------------------------------------------------- A09 audit log


def test_audit_log_records_login_and_failures(client, db, demo_user):
    """A09: Phase 0B had no audit_logs table — attacks left no trace."""
    from app.models.audit_log import (
        ACTION_LOGIN,
        ACTION_LOGIN_FAILED,
        AuditLog,
    )

    client.post(
        "/api/v1/auth/login",
        json={"email": demo_user["email"], "password": demo_user["password"]},
    )
    client.post(
        "/api/v1/auth/login", json={"email": demo_user["email"], "password": "wrong"}
    )
    db.expire_all()
    actions = {row.action for row in db.query(AuditLog).all()}
    assert ACTION_LOGIN in actions
    assert ACTION_LOGIN_FAILED in actions


def test_audit_log_captures_ip_and_user_agent(client, db, demo_user):
    from app.models.audit_log import ACTION_LOGIN, AuditLog

    client.post(
        "/api/v1/auth/login",
        json={"email": demo_user["email"], "password": demo_user["password"]},
        headers={"User-Agent": "phase1-probe/1.0"},
    )
    db.expire_all()
    row = (
        db.query(AuditLog)
        .filter(AuditLog.action == ACTION_LOGIN)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert row is not None
    assert row.ip
    assert "phase1-probe" in row.user_agent


# ------------------------------------------------------- A02 config validation


def test_production_refuses_weak_secret_key(monkeypatch):
    from app.core.config import Settings

    cfg = Settings(
        APP_ENV="production",
        SECRET_KEY=Settings.DEFAULT_SECRET,
        REDIS_URL="redis://localhost:6379/0",
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        cfg.validate_runtime()


def test_production_requires_real_redis():
    from app.core.config import Settings

    cfg = Settings(
        APP_ENV="production", SECRET_KEY="x" * 48, REDIS_URL=""
    )
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        cfg.validate_runtime()


def test_development_config_is_permissive():
    from app.core.config import Settings

    Settings(APP_ENV="development").validate_runtime()  # must not raise
