"""Role home pages (Phase 1 stubs)."""

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from qr_chores.auth.deps import get_current_user, get_current_user_optional, require_role
from qr_chores.models.user import User, UserRole
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
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "parent_today.html",
        {
            "user": user,
            "title": "Today",
        },
    )


@router.get("/home", response_class=HTMLResponse)
async def child_home(
    request: Request,
    user: User = Depends(require_role(UserRole.child)),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "child_home.html",
        {
            "user": user,
            "title": "Home",
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
