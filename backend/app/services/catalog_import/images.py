"""Image acquisition for imported rows: fetch → validate → pHash → own storage.

Why re-host at all? Three reasons, all from the ADR-016 post-mortem:

* **Truth needs a fingerprint.** ``duplicate_image`` works on the perceptual
  hash; a hash needs the bytes.
* **The vision check needs the bytes too** (``detected_category`` is what
  makes ``image_category_mismatch`` possible for a feed row).
* **Hot-linking a seller CDN is fragile** and puts a third-party origin into
  our CSP for every seller. Re-hosting on the platform's own S3/local storage
  keeps ``img-src`` closed and the card rendering when the seller rotates
  keys.

Everything reuses the hardened primitives that already guard admin uploads:
:func:`ai.feature_extractor._fetch_image_bytes` (SSRF-guarded, manual
redirects, local-file mode for offline runs) and
:func:`app.core.uploads.validate_image_upload` (magic bytes, bomb guard,
re-encode, pHash). A feed cannot smuggle anything an upload could not.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from ai.feature_extractor import _fetch_image_bytes
from app.core.storage import get_storage
from app.core.uploads import UploadRejected, validate_image_upload
from app.core.url_safety import UnsafeUrl

logger = logging.getLogger(__name__)

#: A seller photo larger than this is almost certainly not a product picture.
MAX_FEED_IMAGE_BYTES = 12 * 1024 * 1024


class ImageUnavailable(Exception):
    """The image could not be fetched or is not a usable picture. ``code`` is stable."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass
class AcquiredImage:
    data: bytes
    content_type: str
    extension: str
    phash: str
    width: int
    height: int
    original_url: str
    #: Where the platform serves it from once :func:`persist` ran
    #: (``/media/<uuid>.jpg`` or an S3 URL); empty until then.
    hosted_url: str = ""


class _Buffered:
    """Duck-typed ``UploadFile`` so :func:`validate_image_upload` can run on bytes."""

    def __init__(self, filename: str, data: bytes, content_type: str):
        self.filename = filename
        self.content_type = content_type
        self.file = io.BytesIO(data)


def fetch_bytes(url: str, *, timeout: float = 30.0) -> tuple[bytes, str]:
    """SSRF-guarded download (or local read). Raises :class:`ImageUnavailable`."""
    try:
        data, mime = _fetch_image_bytes(url, timeout=timeout)
    except UnsafeUrl as exc:
        raise ImageUnavailable("image_url_unsafe", str(exc)) from exc
    except Exception as exc:  # httpx errors, HTTP 4xx/5xx, OSError on local files
        raise ImageUnavailable("image_unreachable", f"{type(exc).__name__}: {exc}") from exc
    if not data:
        raise ImageUnavailable("image_unreachable", "empty body")
    if len(data) > MAX_FEED_IMAGE_BYTES:
        raise ImageUnavailable("image_too_large", f"{len(data)} bytes")
    return data, mime


def acquire(url: str, *, timeout: float = 30.0, store: bool = False) -> AcquiredImage:
    """Download ``url``, validate it like an admin upload, hash it.

    Nothing is written unless ``store=True``; the pipeline normally calls
    :func:`persist` itself *after* the duplicate check so a skipped twin never
    leaves an orphan object in storage.
    """
    data, mime = fetch_bytes(url, timeout=timeout)
    filename = url.rsplit("/", 1)[-1][:120] or "feed-image"
    try:
        image = validate_image_upload(_Buffered(filename, data, mime))
    except UploadRejected as exc:
        raise ImageUnavailable("image_invalid", str(exc.detail)) from exc
    acquired = AcquiredImage(
        data=image.data,
        content_type=image.content_type,
        extension=image.extension,
        phash=image.phash,
        width=image.width,
        height=image.height,
        original_url=url,
    )
    if store:
        persist(acquired)
    return acquired


def persist(image: AcquiredImage) -> str:
    """Copy the validated bytes to the platform's storage; idempotent per object."""
    if not image.hosted_url:
        image.hosted_url = get_storage().upload_file(
            image.data, f"feed{image.extension}", image.content_type
        )
    return image.hosted_url
