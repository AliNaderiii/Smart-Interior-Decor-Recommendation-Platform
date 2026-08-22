"""S3-compatible storage abstraction.

Routes NEVER touch boto3 directly — they call ``get_storage().upload_file``.
Backends:
  * ``s3``    — any S3-compatible provider (AWS, Arvan, Liara) via env vars.
  * ``local`` — filesystem, for dev/test and CI.
"""
from __future__ import annotations

import mimetypes
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings

#: Stage 03 (T-28/T-31): the object key must never inherit an extension from a
#: client-supplied filename. `app.core.uploads` already normalises it from the
#: sniffed image format, but a storage backend is a shared primitive that any
#: future caller can reach, so it enforces the same rule itself.
SAFE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
DEFAULT_EXTENSION = ".bin"


def safe_extension(filename: str) -> str:
    """Return an allowlisted extension, or `.bin` for anything unrecognised.

    `.bin` is deliberate: an unknown object gets a name a browser will not
    render, so even a misrouted upload cannot become a same-origin HTML
    document.
    """
    suffix = Path(filename or "").suffix.lower()
    # `Path().suffix` cannot contain a separator, but a caller could pass an
    # already-crafted string; belt and braces.
    if "/" in suffix or "\\" in suffix or len(suffix) > 8:
        return DEFAULT_EXTENSION
    return suffix if suffix in SAFE_EXTENSIONS else DEFAULT_EXTENSION


class StorageBackend(ABC):
    @abstractmethod
    def upload_file(self, data: bytes, filename: str, content_type: str | None = None) -> str:
        """Store ``data`` and return a publicly reachable URL."""


class LocalStorage(StorageBackend):
    def __init__(self) -> None:
        self.base = Path(settings.LOCAL_STORAGE_DIR)
        self.base.mkdir(parents=True, exist_ok=True)

    def upload_file(self, data: bytes, filename: str, content_type: str | None = None) -> str:
        key = f"{uuid.uuid4().hex}{safe_extension(filename)}"
        target = (self.base / key).resolve()
        # Containment assertion: the key is generated, so this can only fail if
        # the code above is changed to trust input again. Cheap tripwire.
        if not str(target).startswith(str(self.base.resolve())):
            raise ValueError("refusing to write outside the storage root")
        target.write_bytes(data)
        return f"/media/{key}"


class S3Storage(StorageBackend):
    def __init__(self) -> None:
        import boto3

        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT or None,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION or None,
        )
        self.bucket = settings.S3_BUCKET

    def upload_file(self, data: bytes, filename: str, content_type: str | None = None) -> str:
        key = f"products/{uuid.uuid4().hex}{safe_extension(filename)}"
        ct = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=ct, ACL="public-read"
        )
        base = settings.S3_PUBLIC_BASE_URL or f"{settings.S3_ENDPOINT}/{self.bucket}"
        return f"{base.rstrip('/')}/{key}"


_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _storage
    if _storage is None:
        _storage = S3Storage() if settings.STORAGE_BACKEND == "s3" else LocalStorage()
    return _storage
