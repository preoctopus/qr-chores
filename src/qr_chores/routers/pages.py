"""Role home pages and JSON helpers."""

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from qr_chores.auth.deps import get_current_user, get_current_user_optional, require_role
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.models.chore import ChoreCompletion
from qr_chores.models.rewards import Achievement, UserAchievement
from qr_chores.models.user import User, UserRole
from qr_chores.services.achievements import ICON_CHOICES, criteria_threshold, progress_for
from qr_chores.services.chores import today_board
from qr_chores.services.points import points_balance, points_earned_today
from qr_chores.services.timeutil import format_due_time
from qr_chores.templating import templates

router = APIRouter(tags=["pages"])

ICON_EMOJI = {k: v.split(" ", 1)[0] for k, v in ICON_CHOICES}


@router.get("/")
async def root(user: User | None = Depends(get_current_user_optional)) -> RedirectResponse:
    if user is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    if user.role == UserRole.parent:
        return RedirectResponse("/today", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse("/home", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/help", response_class=HTMLResponse)
async def help_page(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Mobile-friendly in-app user guide (parent + child)."""
    return templates.TemplateResponse(
        request,
        "help.html",
        {
            "user": user,
            "title": "Help",
        },
    )


@router.get("/today", response_class=HTMLResponse)
async def parent_today(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    board = await today_board(db, settings, parent_id=user.id)
    return templates.TemplateResponse(
        request,
        "parent_today.html",
        {
            "user": user,
            "title": "Today",
            "board": board,
            "format_due_time": format_due_time,
        },
    )


@router.get("/home", response_class=HTMLResponse)
async def child_home(
    request: Request,
    user: User = Depends(require_role(UserRole.child)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    points_today = await points_earned_today(db, user.id, settings)
    balance = await points_balance(db, user.id)

    result = await db.execute(
        select(Achievement).where(Achievement.is_active.is_(True)).order_by(Achievement.title)
    )
    achievements = list(result.scalars().all())
    owned = await db.execute(
        select(UserAchievement.achievement_id).where(UserAchievement.user_id == user.id)
    )
    owned_ids = set(owned.scalars().all())

    awarded_rows: list[AchievementRow] = []
    not_awarded_rows: list[AchievementRow] = []
    for ach in achievements:
        threshold = criteria_threshold(ach)
        progress = await progress_for(db, user.id, ach, settings)
        unlocked = ach.id in owned_ids
        row = AchievementRow(
            achievement=ach,
            unlocked=unlocked,
            progress=threshold if unlocked else min(progress, threshold),
            threshold=threshold,
        )
        if unlocked:
            awarded_rows.append(row)
        else:
            not_awarded_rows.append(row)

    return templates.TemplateResponse(
        request,
        "child_home.html",
        {
            "user": user,
            "title": "Home",
            "points_today": points_today,
            "balance": balance,
            "awarded_rows": awarded_rows,
            "not_awarded_rows": not_awarded_rows,
            "icon_emoji": ICON_EMOJI,
            "format_due_time": format_due_time,
        },
    )


@router.get("/history", response_class=HTMLResponse)
async def parent_history(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    result = await db.execute(
        select(ChoreCompletion)
        .options(selectinload(ChoreCompletion.chore))
        .order_by(ChoreCompletion.completed_at.desc())
        .limit(50)
    )
    completions = list(result.scalars().all())
    return templates.TemplateResponse(
        request,
        "parent_history.html",
        {
            "user": user,
            "title": "History",
            "completions": completions,
            "format_due_time": format_due_time,
        },
    )


@dataclass
class AchievementRow:
    achievement: Achievement
    unlocked: bool
    progress: int
    threshold: int

    @property
    def percent(self) -> int:
        if self.threshold <= 0:
            return 100
        return min(100, int(100 * self.progress / self.threshold))


@router.get("/me/achievements", response_class=HTMLResponse)
async def child_achievements(
    request: Request,
    user: User = Depends(require_role(UserRole.child)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    result = await db.execute(
        select(Achievement).where(Achievement.is_active.is_(True)).order_by(Achievement.title)
    )
    achievements = list(result.scalars().all())
    owned = await db.execute(
        select(UserAchievement.achievement_id).where(UserAchievement.user_id == user.id)
    )
    owned_ids = set(owned.scalars().all())
    rows: list[AchievementRow] = []
    for ach in achievements:
        threshold = criteria_threshold(ach)
        progress = await progress_for(db, user.id, ach, settings)
        rows.append(
            AchievementRow(
                achievement=ach,
                unlocked=ach.id in owned_ids,
                progress=min(progress, threshold) if ach.id not in owned_ids else threshold,
                threshold=threshold,
            )
        )
    rows.sort(key=lambda r: (not r.unlocked, r.achievement.title))
    balance = await points_balance(db, user.id)
    return templates.TemplateResponse(
        request,
        "child_achievements.html",
        {
            "user": user,
            "title": "Achievements",
            "rows": rows,
            "unlocked_count": sum(1 for r in rows if r.unlocked),
            "balance": balance,
            "icon_emoji": ICON_EMOJI,
        },
    )


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    """JSON helper useful for tests and debugging."""
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role.value,
    }
