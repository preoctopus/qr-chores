"""Unit tests for photo upload stream helper."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from qr_chores.services.completion import CompletionError
from qr_chores.services.uploads import read_photo_upload


def _upload(data: bytes, *, filename: str | None = "photo.png") -> UploadFile:
    return UploadFile(
        file=BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": "image/png"}),
    )


@pytest.mark.asyncio
async def test_read_photo_upload_none() -> None:
    assert await read_photo_upload(None, max_bytes=1000) is None


@pytest.mark.asyncio
async def test_read_photo_upload_empty_filename() -> None:
    up = _upload(b"abc", filename="")
    assert await read_photo_upload(up, max_bytes=1000) is None


@pytest.mark.asyncio
async def test_read_photo_upload_empty_body() -> None:
    up = _upload(b"", filename="empty.png")
    assert await read_photo_upload(up, max_bytes=1000) is None


@pytest.mark.asyncio
async def test_read_photo_upload_ok() -> None:
    data = b"\x89PNG" + b"x" * 20
    up = _upload(data)
    photo = await read_photo_upload(up, max_bytes=1000)
    assert photo is not None
    assert photo.data == data


@pytest.mark.asyncio
async def test_read_photo_upload_too_large() -> None:
    up = _upload(b"x" * 50)
    with pytest.raises(CompletionError) as exc:
        await read_photo_upload(up, max_bytes=10)
    assert exc.value.code == "too_large"


@pytest.mark.asyncio
async def test_read_photo_upload_chunks_until_limit() -> None:
    """Ensure chunked reads accumulate and trip the cap mid-stream."""
    mock = AsyncMock(spec=UploadFile)
    mock.filename = "big.png"
    mock.content_type = "image/png"
    # first chunk OK, second pushes over max
    mock.read = AsyncMock(side_effect=[b"a" * 8, b"b" * 8, b""])
    with pytest.raises(CompletionError) as exc:
        await read_photo_upload(mock, max_bytes=10)
    assert exc.value.code == "too_large"
