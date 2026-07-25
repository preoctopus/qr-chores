"""Unit tests for local photo storage and validation."""

from pathlib import Path

import pytest

from qr_chores.config import Settings
from qr_chores.services.storage import (
    LocalPhotoStorage,
    StorageError,
    get_photo_storage,
    sniff_content_type,
    validate_and_build_key,
)

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_local_storage_roundtrip(tmp_path: Path) -> None:
    store = LocalPhotoStorage(tmp_path)
    key = "completions/1/2026-07-25/abc.png"
    stored = store.save(key, TINY_PNG, "image/png")
    assert stored.size == len(TINY_PNG)
    data, ctype = store.open(key)
    assert data == TINY_PNG
    assert ctype == "image/png"
    store.delete(key)
    with pytest.raises(StorageError) as exc:
        store.open(key)
    assert exc.value.code == "not_found"


def test_local_storage_rejects_path_traversal(tmp_path: Path) -> None:
    store = LocalPhotoStorage(tmp_path)
    with pytest.raises(StorageError) as exc:
        store.save("../escape.png", b"x", "image/png")
    assert exc.value.code == "bad_key"


def test_get_photo_storage_local(tmp_path: Path) -> None:
    settings = Settings(photo_storage="local", photo_local_dir=str(tmp_path / "up"))
    storage = get_photo_storage(settings)
    assert isinstance(storage, LocalPhotoStorage)


def test_get_photo_storage_gcs_requires_bucket() -> None:
    settings = Settings(photo_storage="gcs", gcs_bucket="")
    with pytest.raises(StorageError) as exc:
        get_photo_storage(settings)
    assert exc.value.code == "config"


def test_validate_and_build_key_ok() -> None:
    settings = Settings(photo_max_bytes=1024 * 1024)
    key, ctype = validate_and_build_key(
        data=TINY_PNG,
        declared_content_type="image/png",
        chore_id=9,
        local_date_str="2026-07-25",
        settings=settings,
    )
    assert ctype == "image/png"
    assert key.startswith("completions/9/2026-07-25/")
    assert key.endswith(".png")


def test_validate_rejects_empty() -> None:
    settings = Settings()
    with pytest.raises(StorageError) as exc:
        validate_and_build_key(
            data=b"",
            declared_content_type=None,
            chore_id=1,
            local_date_str="2026-07-25",
            settings=settings,
        )
    assert exc.value.code == "empty"


def test_validate_rejects_too_large() -> None:
    settings = Settings(photo_max_bytes=10)
    with pytest.raises(StorageError) as exc:
        validate_and_build_key(
            data=TINY_PNG,
            declared_content_type="image/png",
            chore_id=1,
            local_date_str="2026-07-25",
            settings=settings,
        )
    assert exc.value.code == "too_large"


def test_sniff_jpeg() -> None:
    # minimal JPEG SOI + more bytes
    data = b"\xff\xd8\xff" + b"\x00" * 20
    assert sniff_content_type(data, "image/jpeg") == "image/jpeg"


def test_sniff_webp() -> None:
    data = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 8
    assert sniff_content_type(data, None) == "image/webp"
