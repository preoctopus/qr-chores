"""Role home pages and JSON helpers."""

from dataclasses import dataclass
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import get_current_user, get_current_user_optional, require_role
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.models.rewards import Achievement, UserAchievement
from qr_chores.models.user import User, UserRole
from qr_chores.services.achievements import ICON_CHOICES, criteria_threshold, progress_for
from qr_chores.services.chores import today_board
from qr_chores.services.dashboard import build_today_dashboard, get_history_days
from qr_chores.services.points import points_balance, points_earned_today
from qr_chores.services.timeutil import day_label, format_clock, format_due_time, local_today
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
    dashboard = await build_today_dashboard(db, settings, parent_id=user.id)
    return templates.TemplateResponse(
        request,
        "parent_today.html",
        {
            "user": user,
            "title": "Today",
            "dashboard": dashboard,
            "board": dashboard.board,
            "format_due_time": format_due_time,
            "format_clock": lambda dt: format_clock(dt, settings),
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
    board = await today_board(db, settings, assignee_user_id=user.id)

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
            "board": board,
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
    settings: Settings = Depends(get_settings),
    child_id: int | None = None,
    chore_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    timing: str | None = None,
) -> HTMLResponse:
    from datetime import date

    from qr_chores.services.chores import list_all_chores
    from qr_chores.services.completion import get_parent_history
    from qr_chores.services.users import list_children_for_parent

    def _parse(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    parsed_start = _parse(start_date)
    parsed_end = _parse(end_date)

    children = await list_children_for_parent(db, parent_id=user.id)
    chores = await list_all_chores(db, parent_id=user.id)

    # Stats cover the user's filters (all time when no dates are given).
    stats_res = await get_parent_history(
        db,
        settings,
        parent_id=user.id,
        child_id=child_id,
        chore_id=chore_id,
        start_date=parsed_start,
        end_date=parsed_end,
        timing=timing,
        limit=1,
    )
    history = await get_history_days(
        db,
        settings,
        parent_id=user.id,
        child_id=child_id,
        chore_id=chore_id,
        start_date=parsed_start,
        end_date=parsed_end,
        timing=timing,
    )

    filters = {
        "child_id": child_id,
        "chore_id": chore_id,
        "start_date": start_date or "",
        "end_date": end_date or "",
        "timing": timing or "",
    }
    filter_query = urlencode(
        {k: v for k, v in filters.items() if k not in ("start_date", "end_date") and v}
    )
    today = local_today(settings)

    return templates.TemplateResponse(
        request,
        "parent_history.html",
        {
            "user": user,
            "title": "History",
            "history": history,
            "stats": stats_res.stats,
            "children": children,
            "chores": chores,
            "filters": filters,
            "filter_query": filter_query,
            "today": today,
            "day_label": lambda d: day_label(d, today),
            "format_due_time": format_due_time,
            "format_clock": lambda dt: format_clock(dt, settings),
        },
    )


@router.post("/completions/{completion_id}/undo", response_class=RedirectResponse)
async def undo_completion_page(
    completion_id: int,
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    next: str | None = Form(None),
) -> RedirectResponse:
    from contextlib import suppress

    from qr_chores.routers.auth import _safe_next_url
    from qr_chores.services.completion import CompletionError, undo_completion

    with suppress(CompletionError):
        await undo_completion(
            db,
            completion_id=completion_id,
            parent_id=user.id,
            settings=settings,
        )

    target = _safe_next_url(next) if next else "/today"
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


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
