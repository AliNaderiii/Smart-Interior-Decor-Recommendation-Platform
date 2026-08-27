"""CSP / image-host runtime alignment — Stage 2, T-2.4 (closes B-11).

Three guarantees, each of which was previously only a comment in a config
file:

1. **Proxy copy cannot drift** — the Caddyfile's Content-Security-Policy is
   byte-identical to ``build_csp()`` for the reference production deployment
   (the Arvan endpoint documented in .env.example). Change one without the
   other and this file fails CI.
2. **Every catalog image renders under the CSP** — each ``image_url`` in the
   committed 150-product dataset has an origin allowed by ``img-src`` (with
   wildcard-aware matching), for BOTH the default (dev) CSP and the reference
   production CSP. This is the machine-checkable form of "product images load
   with zero CSP violations"; the browser-level capture is deferred to the
   Stage-4 staging environment (no browser in this sandbox, and the vite
   preview used by the CI lighthouse job serves no CSP header at all).
3. **The new image-host knobs actually work** — IMAGE_CDN_BASE_URL and
   IMAGE_EXTRA_ORIGINS feed img-src; S3 endpoints imply their virtual-hosted
   bucket wildcard (the pattern the Caddyfile always allowed but the app copy
   silently dropped — the B-11 drift).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from app.core.config import Settings
from app.core.security_headers import build_csp

REPO_ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = REPO_ROOT / "Caddyfile"
CATALOG = REPO_ROOT / "datasets" / "products_realistic_150.json"


def _reference_csp() -> str:
    """The CSP of the documented production deployment (print_csp --reference)."""
    from scripts.print_csp import REFERENCE_CFG
    return build_csp(REFERENCE_CFG)


def _caddyfile_csp() -> str:
    text = CADDYFILE.read_text(encoding="utf-8")
    m = re.search(r'Content-Security-Policy\s+"([^"]+)"', text)
    assert m, "Caddyfile has no Content-Security-Policy header line"
    return m.group(1)


def _img_sources(csp: str) -> list[str]:
    for directive in csp.split(";"):
        directive = directive.strip()
        if directive.startswith("img-src"):
            return directive.split()[1:]
    raise AssertionError("CSP has no img-src directive")


def _origin_allowed(origin: str, sources: list[str]) -> bool:
    """Wildcard-aware CSP host-source matching (scheme://host level)."""
    scheme, _, host = origin.partition("://")
    for src in sources:
        if src in ("'self'", "data:", "blob:"):
            continue
        s_scheme, _, s_host = src.partition("://")
        if s_scheme != scheme:
            continue
        if s_host == host:
            return True
        if s_host.startswith("*.") and host.endswith(s_host[1:]):
            return True
    return False


# ------------------------------------------------------------ 1. proxy copy

def test_caddyfile_csp_is_byte_identical_to_build_csp_reference():
    assert _caddyfile_csp() == _reference_csp(), (
        "Caddyfile CSP drifted from build_csp(). Regenerate it: "
        "python backend/scripts/print_csp.py --reference"
    )


def test_reference_csp_keeps_the_virtual_hosted_bucket_wildcard():
    sources = _img_sources(_reference_csp())
    assert "https://s3.ir-thr-at1.arvanstorage.ir" in sources
    assert "https://*.s3.ir-thr-at1.arvanstorage.ir" in sources


# ------------------------------------------------- 2. catalog image coverage

def _catalog_origins() -> set[str]:
    rows = json.loads(CATALOG.read_text(encoding="utf-8"))
    origins = set()
    for row in rows:
        url = row.get("image_url", "")
        if url:
            parts = urlsplit(url)
            assert parts.scheme and parts.netloc, f"malformed image_url: {url}"
            origins.add(f"{parts.scheme}://{parts.netloc}")
    assert origins, "catalog has no image URLs — coverage test is vacuous"
    return origins


def test_every_catalog_image_origin_is_allowed_by_the_default_csp():
    sources = _img_sources(build_csp(Settings(SECRET_KEY="k" * 40)))
    for origin in _catalog_origins():
        assert _origin_allowed(origin, sources), (
            f"{origin} would be BLOCKED by the default CSP img-src {sources}"
        )


def test_every_catalog_image_origin_is_allowed_by_the_reference_csp():
    sources = _img_sources(_reference_csp())
    for origin in _catalog_origins():
        assert _origin_allowed(origin, sources), (
            f"{origin} would be BLOCKED in the reference production CSP"
        )


# ------------------------------------------------------- 3. image-host knobs

def test_image_cdn_base_url_feeds_img_src():
    cfg = Settings(SECRET_KEY="k" * 40,
                   IMAGE_CDN_BASE_URL="https://cdn.decor.example/assets")
    sources = _img_sources(build_csp(cfg))
    assert "https://cdn.decor.example" in sources
    assert "https://cdn.decor.example/assets" not in sources, "origin, not URL"


def test_image_extra_origins_feed_img_src():
    cfg = Settings(SECRET_KEY="k" * 40,
                   IMAGE_EXTRA_ORIGINS="https://a.example, https://b.example:8443")
    sources = _img_sources(build_csp(cfg))
    assert "https://a.example" in sources
    assert "https://b.example:8443" in sources


def test_s3_endpoint_implies_virtual_hosted_wildcard():
    cfg = Settings(SECRET_KEY="k" * 40, S3_ENDPOINT="https://s3.example.com")
    sources = _img_sources(build_csp(cfg))
    assert "https://s3.example.com" in sources
    assert "https://*.s3.example.com" in sources


def test_empty_image_settings_add_nothing():
    csp_default = build_csp(Settings(SECRET_KEY="k" * 40))
    assert _img_sources(csp_default) == [
        "'self'", "data:", "blob:", "https://images.unsplash.com"]


def test_wildcard_matcher_rejects_lookalike_hosts():
    sources = ["https://*.s3.example.com"]
    assert _origin_allowed("https://bucket.s3.example.com", sources)
    assert not _origin_allowed("https://evil-s3.example.org", sources)
    assert not _origin_allowed("http://bucket.s3.example.com", sources), "scheme must match"
