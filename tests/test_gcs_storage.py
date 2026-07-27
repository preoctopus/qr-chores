"""GCS photo storage backend tests (mocked google.cloud.storage)."""

from __future__ import annotations

from datetime import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from qr_chores.auth.passwords import hash_password
from qr_chores.config import Settings
from qr_chores.db import Base
from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.models.user import User, UserRole
from qr_chores.services.completion import PhotoUpload, complete_chore
from qr_chores.services.points import set_setting
from qr_chores.services.qr import new_qr_token
from qr_chores.services.storage import (
    GcsPhotoStorage,
    StorageError,
    clear_photo_storage_cache,
    get_photo_storage,
)

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(autouse=True)
def _clear_storage_cache():
    clear_photo_storage_cache()
    yield
    clear_photo_storage_cache()


def _gcs_stack():
    """Mock Client/bucket/blob used by GcsPhotoStorage."""
    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    return mock_client, mock_bucket, mock_blob


def test_get_photo_storage_returns_gcs_backend() -> None:
    mock_client, mock_bucket, _ = _gcs_stack()
    with patch("google.cloud.storage.Client", return_value=mock_client):
        settings = Settings(photo_storage="gcs", gcs_bucket="family-photos")
        store = get_photo_storage(settings)
        assert isinstance(store, GcsPhotoStorage)
        mock_client.bucket.assert_called_with("family-photos")
        assert get_photo_storage(settings) is store


def test_gcs_save_uploads_with_content_type() -> None:
    mock_client, mock_bucket, mock_blob = _gcs_stack()
    with patch("google.cloud.storage.Client", return_value=mock_client):
        store = GcsPhotoStorage("my-bucket")

    key = "completions/1/2026-07-27/abc.png"
    stored = store.save(key, TINY_PNG, "image/png")

    mock_bucket.blob.assert_called_with(key)
    mock_blob.upload_from_string.assert_called_once_with(TINY_PNG, content_type="image/png")
    assert stored.key == key
    assert stored.content_type == "image/png"
    assert stored.size == len(TINY_PNG)


def test_gcs_open_downloads_bytes() -> None:
    mock_client, mock_bucket, mock_blob = _gcs_stack()
    mock_blob.exists.return_value = True
    mock_blob.download_as_bytes.return_value = TINY_PNG
    mock_blob.content_type = "image/png"

    with patch("google.cloud.storage.Client", return_value=mock_client):
        store = GcsPhotoStorage("my-bucket")

    data, ctype = store.open("completions/1/2026-07-27/abc.png")
    assert data == TINY_PNG
    assert ctype == "image/png"
    mock_blob.exists.assert_called_once()
    mock_blob.download_as_bytes.assert_called_once()


def test_gcs_open_missing_raises_not_found() -> None:
    mock_client, mock_bucket, mock_blob = _gcs_stack()
    mock_blob.exists.return_value = False

    with patch("google.cloud.storage.Client", return_value=mock_client):
        store = GcsPhotoStorage("my-bucket")

    with pytest.raises(StorageError) as exc:
        store.open("completions/1/2026-07-27/missing.png")
    assert exc.value.code == "not_found"
    mock_blob.download_as_bytes.assert_not_called()


def test_gcs_open_default_content_type_when_unset() -> None:
    mock_client, mock_bucket, mock_blob = _gcs_stack()
    mock_blob.exists.return_value = True
    mock_blob.download_as_bytes.return_value = b"bytes"
    mock_blob.content_type = None

    with patch("google.cloud.storage.Client", return_value=mock_client):
        store = GcsPhotoStorage("b")

    _, ctype = store.open("k")
    assert ctype == "application/octet-stream"


def test_gcs_delete_existing() -> None:
    mock_client, mock_bucket, mock_blob = _gcs_stack()
    mock_blob.exists.return_value = True

    with patch("google.cloud.storage.Client", return_value=mock_client):
        store = GcsPhotoStorage("my-bucket")

    store.delete("completions/1/x.png")
    mock_blob.delete.assert_called_once()


def test_gcs_delete_missing_is_noop() -> None:
    mock_client, mock_bucket, mock_blob = _gcs_stack()
    mock_blob.exists.return_value = False

    with patch("google.cloud.storage.Client", return_value=mock_client):
        store = GcsPhotoStorage("my-bucket")

    store.delete("completions/1/gone.png")
    mock_blob.delete.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chore_uses_gcs_backend(tmp_path) -> None:
    """Domain complete with PHOTO_STORAGE=gcs (mocked GCS client)."""
    mock_client, mock_bucket, mock_blob = _gcs_stack()
    mock_blob.exists.return_value = True
    mock_blob.download_as_bytes.return_value = TINY_PNG
    mock_blob.content_type = "image/png"

    with patch("google.cloud.storage.Client", return_value=mock_client):
        settings = Settings(
            photo_storage="gcs",
            gcs_bucket="test-bucket",
            app_timezone="America/Chicago",
            photo_local_dir=str(tmp_path / "unused"),
        )
        store = get_photo_storage(settings)
        assert isinstance(store, GcsPhotoStorage)

        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            child = User(
                email="gcs@example.com",
                display_name="G",
                password_hash=hash_password("x"),
                role=UserRole.child,
                is_active=True,
            )
            session.add(child)
            await set_setting(session, "early_bonus_points", "0")
            await set_setting(session, "on_time_bonus_points", "0")
            await set_setting(session, "late_bonus_points", "0")
            chore = Chore(
                title="GCS proof",
                qr_token=new_qr_token(),
                due_time=time(23, 59),
                schedule_days="0123456",
                photo_policy=PhotoPolicy.required,
                base_points=8,
                is_active=True,
            )
            session.add(chore)
            await session.commit()
            await session.refresh(child)
            await session.refresh(chore)

            result = await complete_chore(
                session,
                chore=chore,
                user=child,
                settings=settings,
                photo=PhotoUpload(data=TINY_PNG, content_type="image/png"),
            )

        assert result.already_done is False
        assert result.completion.photo_object_key is not None
        assert result.completion.photo_object_key.startswith("completions/")
        mock_blob.upload_from_string.assert_called()
        upload_args = mock_blob.upload_from_string.call_args
        assert upload_args[0][0] == TINY_PNG
        assert upload_args[1]["content_type"] == "image/png"

        data, ctype = store.open(result.completion.photo_object_key)
        assert data == TINY_PNG
        assert ctype == "image/png"

        await engine.dispose()
