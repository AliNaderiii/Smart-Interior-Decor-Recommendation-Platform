"""Stage 03 · SSRF and URL handling (probe V-03/V-04, T-35 … T-39).

Baseline: `seller_link` accepted `javascript:` and `file://`, and
`check_product_link` fetched whatever it was given — including
`http://169.254.169.254/latest/meta-data/` (cloud instance metadata) and
`http://127.0.0.1:6379/` — then followed redirects to the same places.
"""
from __future__ import annotations

import pytest

from app.core.url_safety import (
    MAX_URL_LENGTH,
    UnsafeUrl,
    is_safe_public_url,
    safe_optional_url,
    validate_public_url,
)

# --------------------------------------------------------------- scheme filter

@pytest.mark.parametrize("url", [
    "javascript:alert(document.domain)",
    "JaVaScRiPt:alert(1)",
    "  javascript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "gopher://127.0.0.1:6379/_SET%20a%20b",
    "ftp://internal.example.com/",
    "dict://127.0.0.1:11211/stat",
])
def test_dangerous_schemes_are_rejected(url):
    with pytest.raises(UnsafeUrl):
        validate_public_url(url)


@pytest.mark.parametrize("url", [
    "https://shop.example.com/product/1",
    "http://shop.example.com/product/1?ref=a",
])
def test_public_http_urls_are_accepted(url):
    assert validate_public_url(url) == url


def test_credentials_in_url_are_rejected():
    """`https://evil.com@internal/` is a classic host-confusion trick."""
    with pytest.raises(UnsafeUrl):
        validate_public_url("https://user:pass@internal.example.com/")


def test_overlong_url_is_rejected():
    with pytest.raises(UnsafeUrl):
        validate_public_url("https://example.com/" + "a" * MAX_URL_LENGTH)


def test_missing_host_is_rejected():
    with pytest.raises(UnsafeUrl):
        validate_public_url("https:///nohost")


# ------------------------------------------------------------- SSRF targets

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:6379/",              # loopback → Redis
    "http://localhost:5432/",              # loopback by name
    "http://[::1]:8000/",                  # IPv6 loopback
    "http://169.254.169.254/latest/meta-data/",   # AWS/GCP IMDS
    "http://[fd00:ec2::254]/latest/meta-data/",   # IPv6 IMDS
    "http://10.0.0.5/internal",            # RFC1918
    "http://172.16.3.9/internal",
    "http://192.168.1.1/admin",
    "http://0.0.0.0:8000/",                # "this host"
    "http://[::ffff:127.0.0.1]/",          # IPv4-mapped IPv6 loopback
    "http://2130706433/",                  # decimal-encoded 127.0.0.1
    "http://metadata.google.internal/computeMetadata/v1/",
])
def test_internal_targets_are_rejected(url):
    with pytest.raises(UnsafeUrl):
        validate_public_url(url, resolve=True)


def test_dns_resolution_to_a_private_address_is_rejected(monkeypatch):
    """DNS rebinding: a public-looking name that answers 127.0.0.1."""
    import socket

    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrl):
        validate_public_url("https://totally-public.example.com/x", resolve=True)


def test_unresolvable_host_is_rejected_when_resolving(monkeypatch):
    import socket

    def boom(*args, **kwargs):
        raise socket.gaierror("nope")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(UnsafeUrl):
        validate_public_url("https://does-not-exist.example.com/", resolve=True)


def test_is_safe_public_url_never_raises():
    assert is_safe_public_url("javascript:alert(1)") is False
    assert is_safe_public_url("https://example.com/") is True


def test_safe_optional_url_allows_empty():
    assert safe_optional_url(None) == ""
    assert safe_optional_url("") == ""
    with pytest.raises(ValueError):
        safe_optional_url("javascript:alert(1)")


# ---------------------------------------------------- schema-level enforcement

def test_product_schema_rejects_javascript_seller_link(client, admin_headers):
    resp = client.post("/api/v1/products", headers=admin_headers, json={
        "title": "Chair", "category": "chair", "price_toman": 1000,
        "image_url": "https://cdn.example.com/c.png",
        "seller_link": "javascript:alert(document.cookie)",
    })
    assert resp.status_code == 422, resp.text


def test_product_schema_rejects_data_uri_image(client, admin_headers):
    resp = client.post("/api/v1/products", headers=admin_headers, json={
        "title": "Chair", "category": "chair", "price_toman": 1000,
        "image_url": "data:text/html,<script>alert(1)</script>",
    })
    assert resp.status_code == 422, resp.text


# ------------------------------------------------------- link checker plumbing

def test_link_checker_refuses_internal_urls_without_making_a_request(monkeypatch,
                                                                    db):
    """The URL is validated *before* any socket is opened."""
    import httpx

    from app.services import link_checker

    def explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("link checker performed a request to an internal URL")

    monkeypatch.setattr(httpx, "Client", explode)
    assert link_checker.check_url("http://169.254.169.254/latest/meta-data/") is False
    assert link_checker.check_url("javascript:alert(1)") is False


def test_link_checker_revalidates_every_redirect_hop(monkeypatch):
    """A 302 to the metadata service must not be followed (T-37)."""
    import socket

    import httpx

    from app.services import link_checker

    # Deterministic DNS: the shop resolves to a public address, so the only
    # thing that can stop the chain is the redirect validation itself.
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
    ])

    hops: list[str] = []

    class FakeResponse:
        def __init__(self, status_code, location=None):
            self.status_code = status_code
            self.headers = {"Location": location} if location else {}
            self.is_redirect = location is not None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert kwargs.get("follow_redirects") is False, (
                "redirects must be followed manually so each hop is validated"
            )

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def head(self, url, **kwargs):
            hops.append(url)
            if len(hops) == 1:
                return FakeResponse(302, "http://169.254.169.254/latest/meta-data/")
            return FakeResponse(200)

        get = head

    monkeypatch.setattr(httpx, "Client", FakeClient)
    assert link_checker.check_url("https://shop.example.com/p/1") is False
    assert hops == ["https://shop.example.com/p/1"], (
        f"the internal redirect target was requested: {hops}"
    )
