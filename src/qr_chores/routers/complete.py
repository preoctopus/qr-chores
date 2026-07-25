"""Child chore completion via QR token."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import get_current_user_optional, require_role
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.models.user import User, UserRole
from qr_chores.services.achievements import ICON_CHOICES
from qr_chores.services.completion import (
    CompletionError,
    PhotoUpload,
    complete_chore,
    get_completion_for_today,
)
from qr_chores.services.timeutil import format_due_time, is_scheduled_on, local_now, local_today
from qr_chores.templating import templates

router = APIRouter(tags=["complete"])

ICON_EMOJI = {k: v.split(" ", 1)[0] for k, v in ICON_CHOICES}


async def _load_chore(db: AsyncSession, token: str) -> Chore | None:
    result = await db.execute(select(Chore).where(Chore.qr_token == token))
    return result.scalar_one_or_none()


async def _read_photo(upload: UploadFile | None) -> PhotoUpload | None:
    if upload is None:
        return None
    # Empty file input still sends a part with empty filename
    if not upload.filename:
        return None
    data = await upload.read()
    if not data:
        return None
    return PhotoUpload(data=data, content_type=upload.content_type)


@router.get("/c/{token}", response_model=None)
async def confirm_page(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_current_user_optional),
):
    if user is None:
        next_url = f"/c/{token}"
        return RedirectResponse(
            f"/login?next={next_url}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if user.role != UserRole.child:
        return templates.TemplateResponse(
            request,
            "complete_error.html",
            {
                "user": user,
                "title": "Wrong account",
                "message": "Log in as the child account to complete chores.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    chore = await _load_chore(db, token)
    if chore is None or not chore.is_active:
        return templates.TemplateResponse(
            request,
            "complete_error.html",
            {
                "user": user,
                "title": "Unknown chore",
                "message": "This QR code doesn’t match an active chore.",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    today = local_today(settings)
    scheduled = is_scheduled_on(chore.schedule_days, today)
    completion = await get_completion_for_today(db, chore, settings)
    now = local_now(settings)
    due_passed = False
    if scheduled and completion is None:
        due_dt = datetime.combine(today, chore.due_time, tzinfo=now.tzinfo)
        due_passed = now > due_dt + timedelta(minutes=settings.on_time_grace_minutes)

    return templates.TemplateResponse(
        request,
        "complete_confirm.html",
        {
            "user": user,
            "title": chore.title,
            "chore": chore,
            "token": token,
            "scheduled": scheduled,
            "completion": completion,
            "due_passed": due_passed,
            "format_due_time": format_due_time,
            "photo_policy": chore.photo_policy,
            "PhotoPolicy": PhotoPolicy,
        },
    )


@router.post("/c/{token}", response_model=None)
async def complete_submit(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(require_role(UserRole.child)),
    photo: UploadFile | None = File(None),
):
    chore = await _load_chore(db, token)
    if chore is None or not chore.is_active:
        return templates.TemplateResponse(
            request,
            "complete_error.html",
            {
                "user": user,
                "title": "Unknown chore",
                "message": "This QR code doesn’t match an active chore.",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    photo_upload = await _read_photo(photo)

    try:
        result = await complete_chore(
            db,
            chore=chore,
            user=user,
            settings=settings,
            photo=photo_upload,
        )
    except CompletionError as exc:
        # Re-show confirm page with error for photo validation issues
        if exc.code in {"photo_required", "bad_type", "too_large", "empty"}:
            today = local_today(settings)
            return templates.TemplateResponse(
                request,
                "complete_confirm.html",
                {
                    "user": user,
                    "title": chore.title,
                    "chore": chore,
                    "token": token,
                    "scheduled": is_scheduled_on(chore.schedule_days, today),
                    "completion": None,
                    "due_passed": False,
                    "format_due_time": format_due_time,
                    "photo_policy": chore.photo_policy,
                    "PhotoPolicy": PhotoPolicy,
                    "error": exc.message,
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return templates.TemplateResponse(
            request,
            "complete_error.html",
            {
                "user": user,
                "title": "Can’t complete",
                "message": exc.message,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return templates.TemplateResponse(
        request,
        "complete_success.html",
        {
            "user": user,
            "title": "Nice!",
            "chore": result.chore,
            "completion": result.completion,
            "already_done": result.already_done,
            "points": result.points,
            "unlocks": result.unlocks,
            "icon_emoji": ICON_EMOJI,
            "format_due_time": format_due_time,
        },
    )
