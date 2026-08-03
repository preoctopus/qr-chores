"""Login / logout routes."""

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import get_current_user_optional
from qr_chores.auth.passwords import verify_password
from qr_chores.auth.session import dump_session
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.logging_setup import log_user_action
from qr_chores.models.user import User, UserRole
from qr_chores.services.auth_rate_limit import get_client_ip, get_login_rate_limiter
from qr_chores.templating import templates

router = APIRouter(tags=["auth"])


def _safe_next_url(next_url: str | None) -> str:
    """Only allow relative same-origin path redirects.

    Rejects absolute URLs, protocol-relative hosts (//evil), and multi-slash
    forms browsers may treat as hosts (///evil.com).
    """
    if not next_url:
        return "/"
    # No backslashes or control characters (open-redirect / header tricks)
    if any(ch in next_url for ch in ("\\", "\n", "\r", "\t", "\0")):
        return "/"
    if not next_url.startswith("/") or next_url.startswith("//"):
        return "/"
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        return "/"
    path = parsed.path or ""
    if not path.startswith("/") or path.startswith("//"):
        return "/"
    # urlparse("///evil.com") → path="/evil.com"; original still dangerous
    path_and_query = next_url.split("#", 1)[0]
    expected = path if not parsed.query else f"{path}?{parsed.query}"
    if path_and_query != expected:
        return "/"
    return expected


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
    client_ip = get_client_ip(request)
    email_clean = email.strip().lower()
    limiter = get_login_rate_limiter()

    if limiter.is_rate_limited(client_ip, email_clean, settings):
        log_user_action("login_rate_limited", detail="html", email=email_clean, ip=client_ip)
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next": next,
                "error": "Too many failed login attempts. Please try again later.",
                "title": "Log in",
                "email": email_clean,
            },
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    result = await db.execute(
        select(User).where(User.email == email_clean, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        limiter.record_failure(client_ip, email_clean, settings)
        log_user_action("login_failed", detail="html", email=email_clean)
        # Re-render form with error (use 401 body via template)
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next": next,
                "error": "Invalid email or password.",
                "title": "Log in",
                "email": email_clean,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    limiter.record_success(client_ip, email_clean)

    destination = _safe_next_url(next) if next else _home_for_role(user.role)
    if destination == "/":
        destination = _home_for_role(user.role)

    is_https = (
        request.headers.get("x-forwarded-proto") == "https"
        or request.url.scheme == "https"
        or (bool(settings.base_url) and settings.base_url.startswith("https://"))
    )
    response = RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=dump_session(settings, user.id),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=is_https,
        path="/",
    )
    log_user_action("login", user_id=user.id, detail="html", role=user.role.value)
    return response


@router.post("/logout")
async def logout(
    user: User | None = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    log_user_action("logout", user_id=user.id if user else None, detail="html")
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response
