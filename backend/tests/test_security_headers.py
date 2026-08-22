"""Stage 03 · security headers, CORS, caching and error envelopes.

Probe H-01 … H-03, C-01 … C-03, T-39 … T-41. The requirement that made the
baseline fail was headers on **error** responses, not just on 200s: an
attacker's traffic is almost entirely 4xx/5xx.
"""
from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.security_headers import STATIC_HEADERS, build_csp

REQUIRED = [
    "Content-Security-Policy",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Permissions-Policy",
    "Cross-Origin-Opener-Policy",
    "Cross-Origin-Resource-Policy",
]


def _assert_hardened(resp):
    for header in REQUIRED:
        assert header in resp.headers, f"{header} missing on {resp.status_code}"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


# --------------------------------------------------------- every status class

def test_headers_on_a_successful_response(client):
    _assert_hardened(client.get("/api/v1/health"))


def test_headers_on_401(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    _assert_hardened(resp)


def test_headers_on_403(client, bearer_headers):
    resp = client.get("/api/v1/admin/users", headers=bearer_headers)
    assert resp.status_code == 403
    _assert_hardened(resp)


def test_headers_on_404(client):
    resp = client.get("/api/v1/definitely-not-a-route")
    assert resp.status_code == 404
    _assert_hardened(resp)


def test_headers_on_405(client):
    resp = client.request("DELETE", "/api/v1/health")
    assert resp.status_code == 405
    _assert_hardened(resp)


def test_headers_on_422(client, bearer_headers):
    resp = client.post("/api/v1/moodboards", headers=bearer_headers,
                       json={"title": "x" * 9999})
    assert resp.status_code == 422
    _assert_hardened(resp)


def test_headers_on_429(client, reset_settings):
    reset_settings(LOGIN_RATE_LIMIT_PER_MINUTE=1)
    for _ in range(3):
        resp = client.post("/api/v1/auth/login",
                           json={"email": "a@example.com", "password": "Wrong123!x"})
    assert resp.status_code == 429
    _assert_hardened(resp)
    assert resp.headers.get("Retry-After")


def test_headers_and_a_clean_envelope_on_500(client, monkeypatch, bearer_headers):
    """H-01: the baseline 500 came back bare, with a traceback-ish body."""
    from app.api.routes import moodboards as mod

    def boom(*args, **kwargs):
        raise RuntimeError("kaboom /home/user/secret/path.py")

    monkeypatch.setattr(mod, "_owned", boom)
    resp = client.get("/api/v1/moodboards/anything", headers=bearer_headers)
    assert resp.status_code == 500
    _assert_hardened(resp)
    body = resp.text.lower()
    assert "kaboom" not in body
    assert "traceback" not in body
    assert "/home/" not in body
    assert resp.json()["success"] is False


# ------------------------------------------------------------------- caching

def test_api_responses_are_never_cached(client, bearer_headers):
    resp = client.get("/api/v1/auth/me", headers=bearer_headers)
    assert resp.headers.get("Cache-Control") == "no-store"
    vary = resp.headers.get("Vary", "")
    for key in ("Cookie", "Authorization", "Origin"):
        assert key in vary, f"Vary must include {key} (got {vary!r})"


def test_server_header_does_not_advertise_the_stack(client):
    server = client.get("/api/v1/health").headers.get("Server", "")
    assert "uvicorn" not in server.lower()
    assert "python" not in server.lower()


# ---------------------------------------------------------------------- CORS

def test_cors_rejects_an_unknown_origin(client):
    resp = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example"
    assert resp.headers.get("access-control-allow-origin") != "*"


def test_cors_preflight_from_an_unknown_origin_is_not_approved(client):
    resp = client.options("/api/v1/auth/login", headers={
        "Origin": "https://evil.example",
        "Access-Control-Request-Method": "POST",
    })
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example"


def test_cors_never_pairs_a_wildcard_with_credentials(client):
    from app.main import build_cors_origins

    origins = build_cors_origins()
    assert "*" not in origins, "allow_credentials=True forbids a wildcard origin"
    assert origins, "at least the SPA origin must be allowed"


def test_cors_allows_the_configured_frontend_origin(client):
    from app.core.config import settings

    resp = client.get("/api/v1/health",
                      headers={"Origin": settings.FRONTEND_ORIGIN})
    assert resp.headers.get("access-control-allow-origin") == settings.FRONTEND_ORIGIN


# ----------------------------------------------------------------------- CSP

def test_csp_has_no_unsafe_inline_script():
    directives = {
        part.strip().split(" ")[0]: part.strip()
        for part in STATIC_HEADERS["Content-Security-Policy"].split(";")
    }
    assert "'unsafe-inline'" not in directives["script-src"]
    assert "'unsafe-eval'" not in directives["script-src"]
    assert directives["frame-ancestors"] == "frame-ancestors 'none'"
    assert directives["object-src"] == "object-src 'none'"
    assert "default-src" in directives
    assert "base-uri" in directives
    assert "form-action" in directives


def test_csp_img_src_follows_the_configured_cdn():
    """IR-005: img-src must describe where images actually come from."""
    cfg = Settings(
        SECRET_KEY="k" * 40,
        S3_PUBLIC_BASE_URL="https://cdn.example.com/bucket",
        S3_ENDPOINT="https://s3.example.com",
    )
    csp = build_csp(cfg)
    assert "https://cdn.example.com" in csp
    assert "https://s3.example.com" in csp
    assert "https://cdn.example.com/bucket" not in csp, "a path is not an origin"


def test_csp_upgrades_insecure_requests_only_in_production():
    dev = Settings(SECRET_KEY="k" * 40, APP_ENV="development")
    prod = Settings(SECRET_KEY="k" * 40, APP_ENV="production")
    assert "upgrade-insecure-requests" not in build_csp(dev)
    assert "upgrade-insecure-requests" in build_csp(prod)


# ------------------------------------------------------------------ docs/HSTS

def test_interactive_docs_are_reachable_outside_production(client):
    assert client.get("/docs").status_code == 200


def test_hsts_is_sent_when_the_request_is_tls_terminated(client):
    resp = client.get("/api/v1/health", headers={"X-Forwarded-Proto": "https"})
    assert "Strict-Transport-Security" in resp.headers
    assert "includeSubDomains" in resp.headers["Strict-Transport-Security"]


def test_production_hides_the_api_surface_map(reset_settings):
    """Rebuild the app under production settings and inspect what it exposes.

    Only `app.main` is reloaded — the `settings` *object* is mutated in place
    and restored — so no other module ends up holding a stale configuration.
    """
    import importlib

    reset_settings(
        APP_ENV="production", SECRET_KEY="p" * 48,
        REDIS_URL="redis://redis:6379/0", COOKIE_SECURE=True,
        FRONTEND_ORIGIN="https://app.example.com",
        FERNET_KEY="2xLmTPRPYxxLW8mM3jXfKcXo5G3iVYkYfQ2vYbFsC8Y=",
        STORAGE_BACKEND="s3", SEED_DEMO_ACCOUNTS=False,
        # Stage 04 remediation: AI_PROVIDER=mock is production-invalid now.
        # Placeholder key value — not a real credential.
        AI_PROVIDER="gemini", GEMINI_API_KEY="test-gemini-key-placeholder",
    )
    import app.main as main_mod

    try:
        importlib.reload(main_mod)
        prod_app = main_mod.app
        assert prod_app.docs_url is None
        assert prod_app.redoc_url is None
        assert prod_app.openapi_url is None
        paths = {getattr(r, "path", "") for r in prod_app.routes}
        assert "/openapi.json" not in paths
        assert "/docs" not in paths
        # T-40: production must not trust developer loopback origins.
        assert main_mod.build_cors_origins() == ["https://app.example.com"]
        assert "/media" not in paths, "local media must not be mounted in production"
    finally:
        pass


@pytest.fixture(autouse=True, scope="module")
def _restore_main_module():
    """Reload `app.main` once the module's production experiment is over."""
    yield
    import importlib

    import app.main as main_mod

    importlib.reload(main_mod)
