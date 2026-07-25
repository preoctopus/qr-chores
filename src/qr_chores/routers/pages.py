"""Role home pages and JSON helpers."""

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import get_current_user, get_current_user_optional, require_role
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.models.user import User, UserRole
from qr_chores.services.chores import today_board
from qr_chores.services.timeutil import format_due_time
from qr_chores.templating import templates

router = APIRouter(tags=["pages"])


@router.get("/")
async def root(user: User | None = Depends(get_current_user_optional)) -> RedirectResponse:
    if user is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    if user.role == UserRole.parent:
        return RedirectResponse("/today", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse("/home", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/today", response_class=HTMLResponse)
async def parent_today(
    request: Request,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    board = await today_board(db, settings)
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
    board = await today_board(db, settings)
    points_today = sum(
        (row.completion.points_awarded if row.completion else 0) for row in board
    )
    done_count = sum(1 for row in board if row.done)
    return templates.TemplateResponse(
        request,
        "child_home.html",
        {
            "user": user,
            "title": "Home",
            "board": board,
            "points_today": points_today,
            "done_count": done_count,
            "total_count": len(board),
            "format_due_time": format_due_time,
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
