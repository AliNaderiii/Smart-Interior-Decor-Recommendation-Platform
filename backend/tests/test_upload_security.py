"""Stage 03 · upload security (probe U-01 … U-05, T-28 … T-34).

Baseline (`04-BEFORE-api-security-probe.txt`) had all five upload checks
INSECURE: an `evil.html` containing `<script>` was accepted and stored with an
attacker-chosen extension, SVG was accepted, a PE binary declared as
`image/jpeg` was accepted, and twelve consecutive uploads all returned 201.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from app.core import uploads
from app.core.storage import LocalStorage, safe_extension

UPLOAD = "/api/v1/products/upload"


def _png(size=(24, 18)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _post(client, headers, name, data, content_type):
    return client.post(UPLOAD, headers=headers,
                       files={"file": (name, data, content_type)})


# ------------------------------------------------------------------ happy path

def test_valid_png_is_accepted(client, admin_headers, png_bytes):
    resp = _post(client, admin_headers, "sofa.png", png_bytes, "image/png")
    assert resp.status_code == 201, resp.text


def test_stored_key_ignores_the_client_filename(client, admin_headers, png_bytes):
    """U-01/U-04: the client's filename must not reach the storage key."""
    resp = _post(client, admin_headers, "../../evil.html", png_bytes, "image/png")
    assert resp.status_code == 201, resp.text
    url = resp.json()["data"]["product"]["image_url"]
    assert "evil" not in url and ".." not in url
    assert url.endswith(".png")


# -------------------------------------------------------------------- rejects

@pytest.mark.parametrize(("name", "payload", "content_type"), [
    # U-01: HTML that would execute as script if served same-origin.
    ("evil.html", b"<html><script>alert(1)</script></html>", "text/html"),
    # U-01 variant: HTML bytes wearing an image content type and extension.
    ("evil.png", b"<html><script>alert(1)</script></html>", "image/png"),
    # U-02: SVG is an executable document format, not a safe raster image.
    ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
     "image/svg+xml"),
    # U-03: a Windows PE binary lying about being a JPEG.
    ("payload.jpg", b"MZ\x90\x00\x03" + b"\x00" * 200, "image/jpeg"),
    # A PHP webshell with a double extension.
    ("shell.php.png", b"<?php system($_GET['c']); ?>", "image/png"),
    # Empty body.
    ("empty.png", b"", "image/png"),
])
def test_dangerous_uploads_are_rejected(client, admin_headers, name, payload,
                                        content_type):
    resp = _post(client, admin_headers, name, payload, content_type)
    assert resp.status_code in (413, 415, 422), (
        f"{name} was accepted with {resp.status_code}"
    )
    assert resp.status_code != 500, "rejection must be a client error, not a crash"


def test_polyglot_png_with_appended_script_is_reencoded(client, admin_headers):
    """A valid PNG with HTML glued on the end must not keep the payload."""
    payload = _png() + b"<script>alert('polyglot')</script>"
    resp = _post(client, admin_headers, "poly.png", payload, "image/png")
    assert resp.status_code == 201, resp.text

    stored = uploads.validate_image_upload(_fake_upload("poly.png", payload,
                                                        "image/png"))
    assert b"<script>" not in stored.data


class _FakeUpload:
    def __init__(self, filename, data, content_type):
        self.filename = filename
        self.content_type = content_type
        self.file = io.BytesIO(data)


def _fake_upload(name, data, content_type):
    return _FakeUpload(name, data, content_type)


# ------------------------------------------------------------------- size caps

def test_oversized_upload_is_413_not_500(client, admin_headers, reset_settings):
    reset_settings(MAX_UPLOAD_BYTES=64 * 1024)
    big = _png(size=(1200, 1200)) + b"\x00" * (128 * 1024)
    resp = _post(client, admin_headers, "big.png", big, "image/png")
    assert resp.status_code == 413, resp.text


def test_read_bounded_stops_before_buffering_everything(reset_settings):
    reset_settings(MAX_UPLOAD_BYTES=1024)
    with pytest.raises(uploads.UploadRejected) as err:
        uploads.read_bounded(_fake_upload("x.bin", b"a" * 5000, "image/png"))
    assert err.value.status_code == 413


def test_decompression_bomb_is_rejected(client, admin_headers, reset_settings):
    """A small file that declares an enormous canvas (T-33)."""
    reset_settings(MAX_UPLOAD_PIXELS=1_000_000, MAX_UPLOAD_EDGE_PX=4000)
    bomb = _png(size=(6000, 6000))  # ~36M pixels, compresses to a few KB
    resp = _post(client, admin_headers, "bomb.png", bomb, "image/png")
    assert resp.status_code == 413, resp.text


# --------------------------------------------------------------- EXIF stripping

def test_exif_gps_is_stripped():
    """T-34: uploading a phone photo must not publish the owner's location."""
    from fractions import Fraction

    image = Image.new("RGB", (40, 40), (7, 7, 7))
    exif = image.getexif()
    exif[0x010F] = "SecretCameraMake"  # Make
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (Fraction(52, 1), Fraction(22, 1), Fraction(0, 1))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", exif=exif)
    raw = buf.getvalue()

    before = Image.open(io.BytesIO(raw)).getexif()
    assert dict(before.get_ifd(0x8825)), "fixture should start with GPS data"

    clean = uploads.validate_image_upload(_fake_upload("p.jpg", raw, "image/jpeg"))
    after = Image.open(io.BytesIO(clean.data)).getexif()
    assert dict(after) == {}
    assert dict(after.get_ifd(0x8825)) == {}
    assert b"SecretCameraMake" not in clean.data


# ------------------------------------------------------------------- rate limit

def test_upload_is_rate_limited_per_admin(client, admin_headers, reset_settings,
                                          png_bytes):
    """U-05: each call costs an AI inference — it must not be free."""
    reset_settings(UPLOAD_RATE_LIMIT_PER_MINUTE=3)
    statuses = [
        _post(client, admin_headers, "s.png", png_bytes, "image/png").status_code
        for _ in range(5)
    ]
    assert 429 in statuses, statuses
    limited = _post(client, admin_headers, "s.png", png_bytes, "image/png")
    assert limited.status_code == 429
    assert limited.headers.get("Retry-After"), "429 must tell the client when to retry"


# -------------------------------------------------------------------- authz

def test_upload_requires_admin(client, bearer_headers, png_bytes):
    resp = _post(client, bearer_headers, "s.png", png_bytes, "image/png")
    assert resp.status_code == 403


def test_upload_requires_authentication(client, png_bytes):
    resp = client.post(UPLOAD, files={"file": ("s.png", png_bytes, "image/png")})
    assert resp.status_code == 401


# ------------------------------------------------------------- storage layer

@pytest.mark.parametrize(("filename", "expected"), [
    ("a.png", ".png"), ("a.JPG", ".jpg"), ("a.jpeg", ".jpeg"), ("a.webp", ".webp"),
    ("a.html", ".bin"), ("a.svg", ".bin"), ("a.php", ".bin"), ("a", ".bin"),
    ("a.png.html", ".bin"), ("../../etc/passwd", ".bin"),
])
def test_safe_extension_allowlist(filename, expected):
    assert safe_extension(filename) == expected


def test_local_storage_cannot_escape_its_root(tmp_path, reset_settings):
    root = tmp_path / "media"
    reset_settings(LOCAL_STORAGE_DIR=str(root))
    store = LocalStorage()
    url = store.upload_file(b"data", "../../../../etc/passwd", "image/png")
    written = list(root.iterdir())
    assert len(written) == 1
    assert written[0].parent == root
    assert written[0].suffix == ".bin"
    assert not (tmp_path.parent / "passwd").exists()
    assert url.startswith("/media/") and ".." not in url


def test_generated_object_key_rejects_hostile_extensions():
    with pytest.raises(ValueError):
        uploads.generated_object_key("../evil")
    with pytest.raises(ValueError):
        uploads.generated_object_key("png")
    assert uploads.generated_object_key(".png").endswith(".png")
