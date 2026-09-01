"""Upload validation and normalisation (Stage 03 — T-28 … T-34).

What was wrong
--------------
``POST /products/upload`` did this::

    data = file.file.read()                     # unbounded read, then check
    if len(data) > 10 * 1024 * 1024: ...        # too late
    url = get_storage().upload_file(data, file.filename, file.content_type)

and ``LocalStorage.upload_file`` derived the stored object's extension from the
**client-supplied filename**. Probe results at baseline:

* ``U-01`` uploading ``evil.html`` containing ``<script>`` returned ``201`` and
  the file was then served back from ``/media/<uuid>.html`` with
  ``Content-Type: text/html`` — **same-origin script execution** against the SPA
  in the local-storage profile.
* ``U-02`` ``image/svg+xml`` accepted. SVG is an executable document format.
* ``U-03`` a PE binary (``MZ`` header) declared as ``image/jpeg`` accepted:
  nothing looked at the bytes.
* ``U-04`` a traversal filename was accepted (the UUID key happened to contain
  it, but nothing asserted containment).
* ``U-05`` twelve uploads in a row all returned ``201``: no throttle on the one
  endpoint that costs an AI inference per call.

Controls implemented here
-------------------------
1. **Bounded streaming read.** The body is consumed in chunks and aborted the
   moment it exceeds ``MAX_UPLOAD_BYTES``; an oversized upload never becomes an
   oversized allocation.
2. **Magic-byte sniffing.** The format comes from the first bytes, never from
   ``Content-Type`` or the filename. Allowlist: PNG, JPEG, WebP, GIF.
3. **Decompression-bomb limits.** Pillow verifies the image and the pixel count
   and edge length are bounded, because a 40 KB PNG can legally declare
   30 000 x 30 000 pixels.
4. **Re-encode.** The image is decoded and re-encoded, which normalises the
   container, drops EXIF (including GPS coordinates — T-34) and destroys any
   polyglot/appended payload.
5. **Generated object key.** ``uuid4 + extension-derived-from-the-sniffed-type``.
   The client's filename never reaches the filesystem or the S3 key.
"""
from __future__ import annotations

import io
import logging
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

logger = logging.getLogger(__name__)

#: sniffed format -> (canonical extension, canonical content type)
ALLOWED_IMAGE_FORMATS: dict[str, tuple[str, str]] = {
    "PNG": (".png", "image/png"),
    "JPEG": (".jpg", "image/jpeg"),
    "WEBP": (".webp", "image/webp"),
    "GIF": (".gif", "image/gif"),
}

#: Magic-byte prefixes, checked before Pillow is asked to parse anything.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"\xff\xd8\xff", "JPEG"),
    (b"GIF87a", "GIF"),
    (b"GIF89a", "GIF"),
)

CHUNK = 64 * 1024


@dataclass(frozen=True)
class ValidatedImage:
    data: bytes
    extension: str
    content_type: str
    width: int
    height: int
    original_filename: str


class UploadRejected(HTTPException):
    """415/413 with a message safe to show a user."""

    def __init__(self, detail: str, code: int = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE):
        super().__init__(code, detail)


def _sniff(head: bytes) -> str | None:
    for prefix, fmt in _MAGIC:
        if head.startswith(prefix):
            return fmt
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    return None


def read_bounded(upload: UploadFile, max_bytes: int | None = None) -> bytes:
    """Read at most ``max_bytes`` + 1, then reject. Never buffers more.

    ``UploadFile.read()`` with no argument materialises the whole body first,
    so the size check that followed it could only ever be cosmetic: by the time
    it ran, the memory had already been allocated. Reading in chunks makes the
    limit real.
    """
    limit = max_bytes or settings.MAX_UPLOAD_BYTES
    buffer = bytearray()
    while True:
        chunk = upload.file.read(CHUNK)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise UploadRejected(
                f"File exceeds the {limit // (1024 * 1024)} MB upload limit",
                status.HTTP_413_CONTENT_TOO_LARGE,
            )
    if not buffer:
        raise UploadRejected("Empty upload", status.HTTP_422_UNPROCESSABLE_CONTENT)
    return bytes(buffer)


def validate_image_upload(upload: UploadFile) -> ValidatedImage:
    """Validate, bound, strip and re-encode an uploaded image.

    Raises :class:`UploadRejected` (415/413/422) — never a 500 — for every
    rejection path, so a malformed upload is a client error with a clear
    message rather than an unhandled decoder exception.
    """
    data = read_bounded(upload)
    declared = (upload.content_type or "").split(";")[0].strip().lower()
    fmt = _sniff(data[:16])
    if fmt is None:
        raise UploadRejected(
            "Unsupported file type: the content does not look like a PNG, "
            "JPEG, WebP or GIF image"
        )
    if declared and declared not in {ct for _, ct in ALLOWED_IMAGE_FORMATS.values()}:
        # Not fatal on its own — the sniff already decided — but a mismatch is
        # worth an audit-able warning because it is a deliberate act.
        logger.warning(
            "upload content-type %r does not match sniffed format %s", declared, fmt
        )

    try:
        from PIL import Image, ImageFile
    except ImportError:  # pragma: no cover - Pillow is a hard requirement
        raise UploadRejected(
            "Image processing unavailable", status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # Refuse to reassemble truncated files: a truncated image is either a
    # transfer error or an attempt to confuse the decoder.
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    # Pillow's own bomb guard, aligned with our configured budget.
    Image.MAX_IMAGE_PIXELS = settings.MAX_UPLOAD_PIXELS

    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()  # structural check; consumes the file object
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ALLOWED_IMAGE_FORMATS:
                raise UploadRejected(f"Unsupported image format: {image.format}")
            width, height = image.size
            if width <= 0 or height <= 0:
                raise UploadRejected("Image has no pixels",
                                     status.HTTP_422_UNPROCESSABLE_CONTENT)
            if max(width, height) > settings.MAX_UPLOAD_EDGE_PX:
                raise UploadRejected(
                    f"Image edge exceeds {settings.MAX_UPLOAD_EDGE_PX}px "
                    f"({width}x{height})",
                    status.HTTP_413_CONTENT_TOO_LARGE,
                )
            if width * height > settings.MAX_UPLOAD_PIXELS:
                raise UploadRejected(
                    f"Image exceeds {settings.MAX_UPLOAD_PIXELS} pixels "
                    f"({width}x{height}) — possible decompression bomb",
                    status.HTTP_413_CONTENT_TOO_LARGE,
                )
            fmt = image.format
            extension, content_type = ALLOWED_IMAGE_FORMATS[fmt]
            clean = _reencode(image, fmt)
    except UploadRejected:
        raise
    except Image.DecompressionBombError as exc:
        # Pillow's own guard fires before ours when the declared canvas is
        # enormous. Report it as "too large", not "not an image", so the
        # operator can tell a bomb apart from a corrupt file.
        logger.warning("rejected decompression bomb: %s", exc)
        raise UploadRejected(
            "Image exceeds the maximum allowed pixel count "
            "— possible decompression bomb",
            status.HTTP_413_CONTENT_TOO_LARGE,
        )
    except Exception as exc:
        logger.warning("rejected upload: %s: %s", exc.__class__.__name__, exc)
        raise UploadRejected("The uploaded file is not a valid image")

    return ValidatedImage(
        data=clean,
        extension=extension,
        content_type=content_type,
        width=width,
        height=height,
        original_filename=(upload.filename or "")[:255],
    )


def _reencode(image, fmt: str) -> bytes:
    """Re-encode to drop EXIF/ICC/appended data (T-34) and kill polyglots."""
    out = io.BytesIO()
    if fmt == "JPEG":
        rgb = image.convert("RGB")
        rgb.save(out, format="JPEG", quality=88, optimize=True)
    elif fmt == "PNG":
        image.convert("RGBA" if "A" in image.getbands() else "RGB").save(
            out, format="PNG", optimize=True
        )
    elif fmt == "WEBP":
        image.save(out, format="WEBP", quality=88, method=4)
    else:  # GIF — keep the palette and any animation frames intact
        image.save(out, format="GIF", save_all=getattr(image, "is_animated", False))
    return out.getvalue()


def generated_object_key(extension: str, prefix: str = "") -> str:
    """A storage key that owes nothing to the client's filename (T-31)."""
    if not extension.startswith(".") or "/" in extension or "\\" in extension:
        raise ValueError(f"refusing to build a key from extension {extension!r}")
    return f"{prefix}{uuid.uuid4().hex}{extension}"
