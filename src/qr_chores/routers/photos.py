"""Authenticated photo serving."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import get_current_user
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.models.chore import ChoreCompletion
from qr_chores.models.user import User
from qr_chores.services.storage import StorageError, get_photo_storage

router = APIRouter(tags=["photos"])


@router.get("/photos/{completion_id}")
async def get_completion_photo(
    completion_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Serve a completion photo to any logged-in family member."""
    result = await db.execute(select(ChoreCompletion).where(ChoreCompletion.id == completion_id))
    completion = result.scalar_one_or_none()
    if completion is None or not completion.photo_object_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    try:
        data, content_type = get_photo_storage(settings).open(completion.photo_object_key)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if exc.code == "not_found" else 400,
            detail=exc.message,
        ) from exc

    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )
