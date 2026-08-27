"""Tests for link_checker.check_url_detailed (Stage 2, T-2.5).

Hermetic: httpx transport is mocked and SSRF validation is stubbed to a
pass-through (URL safety itself is covered by tests/test_url_safety.py).
The boolean facade check_url must keep byte-identical semantics.
"""
from __future__ import annotations

import httpx
import pytest

from app.services import link_checker


@pytest.fixture()
def passthrough_validation(monkeypatch):
    monkeypatch.setattr(link_checker, "validate_public_url",
                        lambda url, resolve=True, field="": url)


def _client_factory(handler):
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client  # captured BEFORE the monkeypatch lands

    def factory(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=transport,
                           **{k: v for k, v in kwargs.items()
                              if k in ("follow_redirects", "timeout", "headers")})
    return factory


def _patch_transport(monkeypatch, handler):
    monkeypatch.setattr(link_checker.httpx, "Client", _client_factory(handler))


def test_direct_200_is_ok(monkeypatch, passthrough_validation):
    _patch_transport(monkeypatch, lambda req: httpx.Response(200))
    r = link_checker.check_url_detailed("https://shop.example/p/1")
    assert r.ok is True
    assert r.classification == "ok"
    assert r.http_status == 200
    assert r.redirect_chain == []
    assert r.latency_ms is not None and r.latency_ms >= 0
    assert link_checker.check_url("https://shop.example/p/1") is True


def test_redirect_then_200_records_chain(monkeypatch, passthrough_validation):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/old":
            return httpx.Response(301, headers={"location": "https://shop.example/new"})
        return httpx.Response(200)
    _patch_transport(monkeypatch, handler)
    r = link_checker.check_url_detailed("https://shop.example/old")
    assert r.ok is True
    assert r.classification == "redirect"
    assert r.redirect_chain == ["https://shop.example/new"]


def test_404_is_dead(monkeypatch, passthrough_validation):
    _patch_transport(monkeypatch, lambda req: httpx.Response(404))
    r = link_checker.check_url_detailed("https://shop.example/gone")
    assert r.ok is False
    assert r.classification == "dead"
    assert r.http_status == 404
    assert link_checker.check_url("https://shop.example/gone") is False


def test_403_after_get_fallback_is_blocked(monkeypatch, passthrough_validation):
    # HEAD 403 triggers the GET fallback; a GET 403 too means a bot wall,
    # classified "blocked" (needs human/egress re-check), not "dead".
    _patch_transport(monkeypatch, lambda req: httpx.Response(403))
    r = link_checker.check_url_detailed("https://shop.example/botwall")
    assert r.ok is False
    assert r.classification == "blocked"
    assert r.http_status == 403


def test_429_is_blocked(monkeypatch, passthrough_validation):
    _patch_transport(monkeypatch, lambda req: httpx.Response(429))
    r = link_checker.check_url_detailed("https://shop.example/ratelimited")
    assert r.classification == "blocked"


def test_redirect_without_location_is_dead(monkeypatch, passthrough_validation):
    _patch_transport(monkeypatch, lambda req: httpx.Response(302))
    r = link_checker.check_url_detailed("https://shop.example/loop")
    assert r.ok is False
    assert r.classification == "dead"
    assert "Location" in r.error


def test_too_many_redirects_is_dead(monkeypatch, passthrough_validation):
    _patch_transport(monkeypatch, lambda req: httpx.Response(
        302, headers={"location": "https://shop.example/next"}))
    r = link_checker.check_url_detailed("https://shop.example/chain")
    assert r.ok is False
    assert r.classification == "dead"
    assert r.error == "too many redirects"
    assert len(r.redirect_chain) == 5


def test_network_error_is_error(monkeypatch, passthrough_validation):
    def handler(req):
        raise httpx.ConnectError("connection refused")
    _patch_transport(monkeypatch, handler)
    r = link_checker.check_url_detailed("https://shop.example/down")
    assert r.ok is False
    assert r.classification == "error"
    assert "ConnectError" in r.error
    assert link_checker.check_url("https://shop.example/down") is False


def test_unsafe_url_never_fetched(monkeypatch):
    def boom(req):  # transport must never be reached
        raise AssertionError("unsafe URL was fetched")
    _patch_transport(monkeypatch, boom)
    r = link_checker.check_url_detailed("http://169.254.169.254/latest/meta-data/")
    assert r.ok is False
    assert r.classification == "unsafe"


def test_unsafe_redirect_blocked(monkeypatch):
    calls = {"n": 0}
    real_validate = link_checker.validate_public_url

    def validate(url, resolve=True, field=""):
        calls["n"] += 1
        if calls["n"] == 1:
            return url  # first hop allowed
        return real_validate(url, resolve=resolve, field=field)  # hop 2: real SSRF check

    monkeypatch.setattr(link_checker, "validate_public_url", validate)
    _patch_transport(monkeypatch, lambda req: httpx.Response(
        302, headers={"location": "http://127.0.0.1:6379/"}))
    r = link_checker.check_url_detailed("https://shop.example/evil")
    assert r.ok is False
    assert r.classification == "unsafe"
    assert "unsafe redirect" in r.error


def test_empty_url_is_dead():
    r = link_checker.check_url_detailed("")
    assert r.ok is False
    assert r.classification == "dead"


def test_as_dict_roundtrip(monkeypatch, passthrough_validation):
    _patch_transport(monkeypatch, lambda req: httpx.Response(200))
    d = link_checker.check_url_detailed("https://shop.example/p/1").as_dict()
    assert set(d) == {"url", "ok", "classification", "http_status",
                      "latency_ms", "redirect_chain", "error"}
