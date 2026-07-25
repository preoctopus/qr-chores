"""Photo storage backends: local disk (dev) and Google Cloud Storage (prod)."""

from __future__ import annotations

import mimetypes
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from qr_chores.config import Settings

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

# Sniff magic bytes when content-type is untrusted
_MAGIC: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),  # further check below
]


class StorageError(Exception):
    def __init__(self, message: str, code: str = "storage") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class StoredPhoto:
    key: str
    content_type: str
    size: int


class PhotoStorage(Protocol):
    def save(self, key: str, data: bytes, content_type: str) -> StoredPhoto: ...

    def open(self, key: str) -> tuple[bytes, str]: ...

    def delete(self, key: str) -> None: ...


class LocalPhotoStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Reject empty / absolute / traversal keys before resolve
        if not key or key.startswith(("/", "\\")) or ".." in Path(key).parts:
            raise StorageError("Invalid photo key.", "bad_key")
        path = (self.root / key).resolve()
        # is_relative_to avoids the classic startswith prefix bug
        # (e.g. root /uploads vs sibling /uploads_evil)
        if path != self.root and not path.is_relative_to(self.root):
            raise StorageError("Invalid photo key.", "bad_key")
        return path

    def save(self, key: str, data: bytes, content_type: str) -> StoredPhoto:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredPhoto(key=key, content_type=content_type, size=len(data))

    def open(self, key: str) -> tuple[bytes, str]:
        path = self._path(key)
        if not path.is_file():
            raise StorageError("Photo not found.", "not_found")
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        # Prefer extension map
        for ct, ext in ALLOWED_CONTENT_TYPES.items():
            if path.suffix.lower() == ext:
                content_type = ct
                break
        return data, content_type

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()


class GcsPhotoStorage:
    def __init__(self, bucket_name: str) -> None:
        from google.cloud import storage as gcs

        self._client = gcs.Client()
        self._bucket = self._client.bucket(bucket_name)

    def save(self, key: str, data: bytes, content_type: str) -> StoredPhoto:
        blob = self._bucket.blob(key)
        blob.upload_from_string(data, content_type=content_type)
        return StoredPhoto(key=key, content_type=content_type, size=len(data))

    def open(self, key: str) -> tuple[bytes, str]:
        blob = self._bucket.blob(key)
        if not blob.exists():
            raise StorageError("Photo not found.", "not_found")
        data = blob.download_as_bytes()
        content_type = blob.content_type or "application/octet-stream"
        return data, content_type

    def delete(self, key: str) -> None:
        blob = self._bucket.blob(key)
        if blob.exists():
            blob.delete()


@lru_cache(maxsize=8)
def _storage_for(backend: str, local_dir: str, gcs_bucket: str) -> PhotoStorage:
    if backend == "gcs":
        if not gcs_bucket:
            raise StorageError("GCS_BUCKET is required when PHOTO_STORAGE=gcs.", "config")
        return GcsPhotoStorage(gcs_bucket)
    return LocalPhotoStorage(Path(local_dir))


def get_photo_storage(settings: Settings) -> PhotoStorage:
    """Return a cached storage backend for the given settings."""
    backend = (settings.photo_storage or "local").lower()
    return _storage_for(backend, settings.photo_local_dir, settings.gcs_bucket or "")


def clear_photo_storage_cache() -> None:
    """Drop cached backends (tests that change PHOTO_* settings)."""
    _storage_for.cache_clear()


def sniff_content_type(data: bytes, declared: str | None) -> str:
    """Return a trusted content type or raise."""
    detected: str | None = None
    if data.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        detected = "image/webp"

    if detected is None:
        raise StorageError(
            "Photo must be a JPEG, PNG, or WebP image.",
            "bad_type",
        )

    # Trust magic bytes; declared content-type is informational only.
    _ = declared
    return detected


def validate_and_build_key(
    *,
    data: bytes,
    declared_content_type: str | None,
    chore_id: int,
    local_date_str: str,
    settings: Settings,
) -> tuple[str, str]:
    if not data:
        raise StorageError("Empty photo file.", "empty")
    if len(data) > settings.photo_max_bytes:
        max_mb = settings.photo_max_bytes // (1024 * 1024)
        raise StorageError(f"Photo is too large (max {max_mb} MB).", "too_large")

    content_type = sniff_content_type(data, declared_content_type)
    ext = ALLOWED_CONTENT_TYPES[content_type]
    key = f"completions/{chore_id}/{local_date_str}/{uuid.uuid4().hex}{ext}"
    return key, content_type
