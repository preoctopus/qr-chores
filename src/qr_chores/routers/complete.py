"""Child chore completion via QR token."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import get_current_user_optional, require_role
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.logging_setup import log_user_action
from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.models.user import User, UserRole
from qr_chores.services.achievements import ICON_CHOICES
from qr_chores.services.completion import (
    CompletionError,
    complete_chore,
    get_completion_for_today,
)
from qr_chores.services.timeutil import (
    format_due_time,
    is_scheduled_on,
    local_now,
    local_today,
    timing_bonus_label,
    timing_rules_intro,
    timing_rules_lines,
    timing_status_label,
)
from qr_chores.services.uploads import read_photo_upload
from qr_chores.templating import templates

router = APIRouter(tags=["complete"])

ICON_EMOJI = {k: v.split(" ", 1)[0] for k, v in ICON_CHOICES}


async def _load_chore(db: AsyncSession, token: str) -> Chore | None:
    result = await db.execute(select(Chore).where(Chore.qr_token == token))
    return result.scalar_one_or_none()


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
    if chore.assignee_user_id is not None and chore.assignee_user_id != user.id:
        return templates.TemplateResponse(
            request,
            "complete_error.html",
            {
                "user": user,
                "title": "Not your chore",
                "message": "This chore is assigned to someone else in the family.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
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
            "timing_status_label": timing_status_label,
            "timing_rules_intro": timing_rules_intro(due_time=chore.due_time),
            "timing_rules": timing_rules_lines(settings, due_time=chore.due_time),
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
    notes: str | None = Form(None),
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
    if chore.assignee_user_id is not None and chore.assignee_user_id != user.id:
        return templates.TemplateResponse(
            request,
            "complete_error.html",
            {
                "user": user,
                "title": "Not your chore",
                "message": "This chore is assigned to someone else in the family.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # Capture ids before complete_chore: IntegrityError + rollback expires ORM
    # instances in this session (user/chore become unsafe to attribute-load).
    user_id = user.id
    chore_id = chore.id
    try:
        photo_upload = await read_photo_upload(photo, max_bytes=settings.photo_max_bytes)
        result = await complete_chore(
            db,
            chore=chore,
            user=user,
            settings=settings,
            photo=photo_upload,
            notes=notes,
        )
        timing = result.completion.timing
        log_user_action(
            "chore_complete",
            user_id=user_id,
            detail="html",
            chore_id=chore_id,
            timing=getattr(timing, "value", timing),
            points=result.completion.points_awarded,
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
                    "timing_status_label": timing_status_label,
                    "timing_rules_intro": timing_rules_intro(due_time=chore.due_time),
                    "timing_rules": timing_rules_lines(settings, due_time=chore.due_time),
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
            "timing_status_label": timing_status_label,
            "timing_bonus_label": timing_bonus_label,
            "timing_rules_intro": timing_rules_intro(due_time=result.chore.due_time),
            "timing_rules": timing_rules_lines(settings, due_time=result.chore.due_time),
        },
    )
