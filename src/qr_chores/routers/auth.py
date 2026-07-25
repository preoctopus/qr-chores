"""Login / logout routes."""

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import get_current_user_optional
from qr_chores.auth.passwords import verify_password
from qr_chores.auth.session import dump_session
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.models.user import User, UserRole
from qr_chores.templating import templates

router = APIRouter(tags=["auth"])


def _safe_next_url(next_url: str | None) -> str:
    """Only allow relative same-origin redirects."""
    if not next_url:
        return "/"
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        return "/"
    if not next_url.startswith("/"):
        return "/"
    return next_url


def _home_for_role(role: UserRole) -> str:
    if role == UserRole.parent:
        return "/today"
    return "/home"


@router.get("/login", response_model=None)
async def login_form(
    request: Request,
    next: str | None = None,
    error: str | None = None,
    user: User | None = Depends(get_current_user_optional),
):
    if user is not None:
        return RedirectResponse(_home_for_role(user.role), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "next": next or "",
            "error": error,
            "title": "Log in",
        },
    )


@router.post("/login", response_model=None)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    result = await db.execute(
        select(User).where(User.email == email.strip().lower(), User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        # Re-render form with error (use 401 body via template)
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next": next,
                "error": "Invalid email or password.",
                "title": "Log in",
                "email": email.strip().lower(),
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    destination = _safe_next_url(next) if next else _home_for_role(user.role)
    if destination == "/":
        destination = _home_for_role(user.role)

    response = RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=dump_session(settings, user.id),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.base_url.startswith("https://"),
        path="/",
    )
    return response


@router.post("/logout")
async def logout(
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response


@router.get("/logout")
async def logout_get(
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Allow GET logout for simple nav links."""
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response
