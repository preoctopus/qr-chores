"""Upload stream helpers (photo size caps)."""

from fastapi import UploadFile

from qr_chores.services.completion import CompletionError, PhotoUpload


async def read_photo_upload(
    upload: UploadFile | None,
    *,
    max_bytes: int,
) -> PhotoUpload | None:
    """Read upload in chunks; refuse bodies larger than max_bytes."""
    if upload is None:
        return None
    # Empty file input still sends a part with empty filename
    if not upload.filename:
        return None

    chunks: list[bytes] = []
    total = 0
    chunk_size = 64 * 1024
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            max_mb = max(1, max_bytes // (1024 * 1024))
            raise CompletionError(
                f"Photo is too large (max {max_mb} MB).",
                "too_large",
            )
        chunks.append(chunk)

    if not chunks:
        return None
    return PhotoUpload(data=b"".join(chunks), content_type=upload.content_type)
