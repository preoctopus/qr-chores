"""Parent rewards configuration: bonuses and achievements."""

import json

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import require_role
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.models.rewards import Achievement, CriteriaType
from qr_chores.models.user import User, UserRole
from qr_chores.services.achievements import (
    CRITERIA_LABELS,
    ICON_CHOICES,
    ensure_default_achievements,
)
from qr_chores.services.points import DEFAULT_BONUSES, get_timing_bonuses, set_setting
from qr_chores.services.timeutil import timing_rules_intro, timing_rules_lines
from qr_chores.templating import templates

router = APIRouter(tags=["rewards"])


@router.get("/rewards", response_model=None)
async def rewards_home(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    await ensure_default_achievements(db)
    await db.commit()
    bonuses = await get_timing_bonuses(db)
    result = await db.execute(
        select(Achievement).order_by(Achievement.is_active.desc(), Achievement.title)
    )
    achievements = list(result.scalars().all())
    return templates.TemplateResponse(
        request,
        "rewards.html",
        {
            "user": user,
            "title": "Rewards",
            "bonuses": bonuses,
            "achievements": achievements,
            "criteria_labels": CRITERIA_LABELS,
            "icon_choices": dict(ICON_CHOICES),
            "timing_rules_intro": timing_rules_intro(),
            "timing_rules": timing_rules_lines(settings),
            "early_window_minutes": settings.early_window_minutes,
            "on_time_grace_minutes": settings.on_time_grace_minutes,
        },
    )


@router.post("/rewards/bonuses", response_model=None)
async def rewards_save_bonuses(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    data = await request.form()
    for key in DEFAULT_BONUSES:
        raw = str(data.get(key) or DEFAULT_BONUSES[key])
        try:
            val = max(0, int(raw))
        except ValueError:
            val = int(DEFAULT_BONUSES[key])
        await set_setting(db, key, str(val))
    await db.commit()
    return RedirectResponse("/rewards", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/rewards/achievements/new", response_model=None)
async def achievement_new_form(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
):
    return templates.TemplateResponse(
        request,
        "achievement_form.html",
        {
            "user": user,
            "title": "New achievement",
            "achievement": None,
            "form": {
                "title": "",
                "description": "",
                "icon_key": "star",
                "criteria_type": CriteriaType.total_completions.value,
                "threshold": "5",
                "points_reward": "10",
            },
            "criteria_types": list(CriteriaType),
            "criteria_labels": CRITERIA_LABELS,
            "icon_choices": ICON_CHOICES,
            "error": None,
        },
    )


def _criteria_json(criteria_type: CriteriaType, threshold: int) -> str:
    if criteria_type == CriteriaType.streak_days:
        return json.dumps({"days": threshold})
    return json.dumps({"count": threshold})


def _threshold_from_achievement(ach: Achievement) -> int:
    try:
        data = json.loads(ach.criteria_json or "{}")
    except json.JSONDecodeError:
        return 1
    return int(data.get("count", data.get("days", 1)))


@router.post("/rewards/achievements", response_model=None)
async def achievement_create(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    data = await request.form()
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    icon_key = str(data.get("icon_key") or "star")
    criteria_type_raw = str(data.get("criteria_type") or "")
    try:
        threshold = max(1, int(str(data.get("threshold") or "1")))
        points_reward = max(0, int(str(data.get("points_reward") or "0")))
        criteria_type = CriteriaType(criteria_type_raw)
    except (ValueError, KeyError):
        return templates.TemplateResponse(
            request,
            "achievement_form.html",
            {
                "user": user,
                "title": "New achievement",
                "achievement": None,
                "form": dict(data),
                "criteria_types": list(CriteriaType),
                "criteria_labels": CRITERIA_LABELS,
                "icon_choices": ICON_CHOICES,
                "error": "Invalid criteria or numbers.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not title:
        return templates.TemplateResponse(
            request,
            "achievement_form.html",
            {
                "user": user,
                "title": "New achievement",
                "achievement": None,
                "form": {
                    "title": title,
                    "description": description,
                    "icon_key": icon_key,
                    "criteria_type": criteria_type.value,
                    "threshold": str(threshold),
                    "points_reward": str(points_reward),
                },
                "criteria_types": list(CriteriaType),
                "criteria_labels": CRITERIA_LABELS,
                "icon_choices": ICON_CHOICES,
                "error": "Title is required.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    ach = Achievement(
        title=title,
        description=description,
        icon_key=icon_key,
        criteria_type=criteria_type,
        criteria_json=_criteria_json(criteria_type, threshold),
        points_reward=points_reward,
        is_active=True,
    )
    db.add(ach)
    await db.commit()
    return RedirectResponse("/rewards", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/rewards/achievements/{achievement_id}/edit", response_model=None)
async def achievement_edit_form(
    request: Request,
    achievement_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    ach = await db.get(Achievement, achievement_id)
    if ach is None:
        return RedirectResponse("/rewards", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "achievement_form.html",
        {
            "user": user,
            "title": f"Edit {ach.title}",
            "achievement": ach,
            "form": {
                "title": ach.title,
                "description": ach.description,
                "icon_key": ach.icon_key,
                "criteria_type": ach.criteria_type.value,
                "threshold": str(_threshold_from_achievement(ach)),
                "points_reward": str(ach.points_reward),
            },
            "criteria_types": list(CriteriaType),
            "criteria_labels": CRITERIA_LABELS,
            "icon_choices": ICON_CHOICES,
            "error": None,
        },
    )


@router.post("/rewards/achievements/{achievement_id}/edit", response_model=None)
async def achievement_edit(
    request: Request,
    achievement_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    ach = await db.get(Achievement, achievement_id)
    if ach is None:
        return RedirectResponse("/rewards", status_code=status.HTTP_303_SEE_OTHER)
    data = await request.form()
    title = str(data.get("title") or "").strip()
    try:
        threshold = max(1, int(str(data.get("threshold") or "1")))
        points_reward = max(0, int(str(data.get("points_reward") or "0")))
        criteria_type = CriteriaType(str(data.get("criteria_type") or ""))
    except (ValueError, KeyError):
        return RedirectResponse("/rewards", status_code=status.HTTP_303_SEE_OTHER)
    if title:
        ach.title = title
    ach.description = str(data.get("description") or "").strip()
    ach.icon_key = str(data.get("icon_key") or "star")
    ach.criteria_type = criteria_type
    ach.criteria_json = _criteria_json(criteria_type, threshold)
    ach.points_reward = points_reward
    await db.commit()
    return RedirectResponse("/rewards", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/rewards/achievements/{achievement_id}/toggle", response_model=None)
async def achievement_toggle(
    achievement_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
):
    ach = await db.get(Achievement, achievement_id)
    if ach is not None:
        ach.is_active = not ach.is_active
        await db.commit()
    return RedirectResponse("/rewards", status_code=status.HTTP_303_SEE_OTHER)
