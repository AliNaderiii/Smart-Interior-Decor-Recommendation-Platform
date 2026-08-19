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


class StorageBackend(ABC):
    @abstractmethod
    def upload_file(self, data: bytes, filename: str, content_type: str | None = None) -> str:
        """Store ``data`` and return a publicly reachable URL."""


class LocalStorage(StorageBackend):
    def __init__(self) -> None:
        self.base = Path(settings.LOCAL_STORAGE_DIR)
        self.base.mkdir(parents=True, exist_ok=True)

    def upload_file(self, data: bytes, filename: str, content_type: str | None = None) -> str:
        ext = Path(filename).suffix or ".bin"
        key = f"{uuid.uuid4().hex}{ext}"
        (self.base / key).write_bytes(data)
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
        ext = Path(filename).suffix or ".bin"
        key = f"products/{uuid.uuid4().hex}{ext}"
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
