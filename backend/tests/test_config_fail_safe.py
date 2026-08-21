"""Stage 03 · configuration fail-safes and fail-closed security controls.

Probe D-01, T-25, T-26, T-45. Two questions:
  1. does the app *refuse to start* on an insecure production configuration?
  2. when Redis is down, does production reject traffic (fail closed) instead
     of quietly disabling every throttle and lockout (fail open)?
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core import brute_force, rate_limit, redis_client
from app.core.config import Settings

VALID_PROD = dict(
    APP_ENV="production",
    SECRET_KEY="s" * 48,
    REDIS_URL="redis://redis:6379/0",
    COOKIE_SECURE=True,
    FRONTEND_ORIGIN="https://app.example.com",
    FERNET_KEY="2xLmTPRPYxxLW8mM3jXfKcXo5G3iVYkYfQ2vYbFsC8Y=",
    STORAGE_BACKEND="s3",
    SEED_DEMO_ACCOUNTS=False,
    AI_PROVIDER="mock",
)


def _prod(**overrides) -> Settings:
    return Settings(**{**VALID_PROD, **overrides})


# ------------------------------------------------------------- boot fail-fast

def test_a_correct_production_configuration_boots():
    _prod().validate_runtime()


@pytest.mark.parametrize(("override", "expected"), [
    ({"SECRET_KEY": "short"}, "SECRET_KEY"),
    ({"SECRET_KEY": "change-me-in-production"}, "SECRET_KEY"),
    ({"REDIS_URL": ""}, "REDIS_URL"),
    ({"COOKIE_SECURE": False}, "COOKIE_SECURE"),
    ({"FRONTEND_ORIGIN": "http://app.example.com"}, "FRONTEND_ORIGIN"),
    ({"FERNET_KEY": ""}, "FERNET_KEY"),
    ({"FERNET_KEY": "not-a-valid-key"}, "FERNET_KEY"),
    ({"STORAGE_BACKEND": "local"}, "STORAGE_BACKEND"),
    ({"SEED_DEMO_ACCOUNTS": True}, "SEED_DEMO_ACCOUNTS"),
    ({"AI_PROVIDER": "gemini"}, "AI_PROVIDER"),
    ({"COOKIE_SAMESITE": "none", "COOKIE_SECURE": False}, "COOKIE_SAMESITE"),
])
def test_insecure_production_settings_refuse_to_boot(override, expected):
    with pytest.raises(RuntimeError, match=expected):
        _prod(**override).validate_runtime()


def test_all_problems_are_reported_at_once():
    """An operator should not have to fix these one restart at a time."""
    with pytest.raises(RuntimeError) as err:
        _prod(SECRET_KEY="x", REDIS_URL="", COOKIE_SECURE=False,
              STORAGE_BACKEND="local").validate_runtime()
    message = str(err.value)
    for expected in ("SECRET_KEY", "REDIS_URL", "COOKIE_SECURE", "STORAGE_BACKEND"):
        assert expected in message


def test_a_non_hmac_jwt_algorithm_is_refused_in_every_environment():
    """Algorithm confusion is not safer in development."""
    for env in ("development", "test", "production"):
        cfg = Settings(APP_ENV=env, SECRET_KEY="s" * 48, JWT_ALGORITHM="none")
        with pytest.raises(RuntimeError, match="JWT_ALGORITHM"):
            cfg.validate_runtime()


def test_development_defaults_do_not_block_a_developer():
    Settings(APP_ENV="development", SECRET_KEY="dev").validate_runtime()


def test_error_message_never_prints_the_secret():
    with pytest.raises(RuntimeError) as err:
        _prod(SECRET_KEY="hunter2hunter2").validate_runtime()
    assert "hunter2hunter2" not in str(err.value)


# -------------------------------------------------------- redis fallback lock

def test_production_refuses_the_in_process_fake_redis(reset_settings, monkeypatch):
    """T-26: per-worker fakeredis silently multiplies every limit by N."""
    monkeypatch.setattr(redis_client, "_client", None)
    reset_settings(APP_ENV="production", REDIS_URL="")
    with pytest.raises(redis_client.RedisUnavailable):
        redis_client.get_redis()
    monkeypatch.setattr(redis_client, "_client", None)


def test_development_still_gets_a_working_fallback(reset_settings, monkeypatch):
    monkeypatch.setattr(redis_client, "_client", None)
    reset_settings(APP_ENV="development", REDIS_URL="")
    client = redis_client.get_redis()
    assert client.ping()
    monkeypatch.setattr(redis_client, "_client", None)


# ------------------------------------------------------------- fail closed

class _BrokenRedis:
    """Every operation raises, as a downed or failing-over Redis would."""

    def __getattr__(self, _name):
        def _raise(*args, **kwargs):
            raise ConnectionError("redis is down")
        return _raise


@pytest.fixture()
def broken_redis(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_redis", lambda: _BrokenRedis())
    monkeypatch.setattr(brute_force, "get_redis", lambda: _BrokenRedis())


def test_rate_limiter_fails_closed_in_production(broken_redis, reset_settings):
    reset_settings(APP_ENV="production")
    with pytest.raises(HTTPException) as err:
        rate_limit.enforce_rate_limit("login:1.2.3.4", limit=5)
    assert err.value.status_code == 503
    assert err.value.headers.get("Retry-After")


def test_rate_limiter_fails_open_in_development(broken_redis, reset_settings,
                                                caplog):
    reset_settings(APP_ENV="development")
    rate_limit.enforce_rate_limit("login:1.2.3.4", limit=5)  # must not raise
    assert "failing open" in caplog.text.lower()


def test_brute_force_check_fails_closed_in_production(broken_redis,
                                                      reset_settings):
    reset_settings(APP_ENV="production")
    with pytest.raises(HTTPException) as err:
        brute_force.check_not_blocked("1.2.3.4", "victim@example.com")
    assert err.value.status_code == 503


def test_brute_force_check_fails_open_in_development(broken_redis,
                                                     reset_settings):
    reset_settings(APP_ENV="development")
    brute_force.check_not_blocked("1.2.3.4", "victim@example.com")


def test_login_returns_503_not_an_open_door_when_redis_is_down(
        client, demo_user, broken_redis, reset_settings):
    """End-to-end: the whole point of failing closed."""
    reset_settings(APP_ENV="production")
    resp = client.post("/api/v1/auth/login", json=demo_user)
    assert resp.status_code == 503, resp.text
    assert resp.headers.get("Retry-After")
    assert "Content-Security-Policy" in resp.headers


def test_login_still_works_in_development_when_redis_is_down(
        client, demo_user, broken_redis, reset_settings):
    """A developer without Redis must not be locked out of their own app."""
    reset_settings(APP_ENV="development")
    resp = client.post("/api/v1/auth/login", json=demo_user)
    assert resp.status_code == 200, resp.text


def test_disabled_limit_is_a_no_op(reset_settings):
    rate_limit.enforce_rate_limit("anything", limit=0)


# ------------------------------------------------------------ shared-backend

def test_is_shared_backend_reflects_the_configuration(reset_settings):
    reset_settings(REDIS_URL="redis://localhost:6379/0")
    assert redis_client.is_shared_backend() is True
    reset_settings(REDIS_URL="")
    assert redis_client.is_shared_backend() is False
