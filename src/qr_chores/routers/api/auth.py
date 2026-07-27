"""API auth: login, logout, me."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import get_current_user, get_current_user_optional
from qr_chores.auth.passwords import verify_password
from qr_chores.auth.session import dump_api_token, dump_session
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.logging_setup import log_user_action
from qr_chores.models.user import User
from qr_chores.schemas.auth import LoginRequest, TokenResponse, UserOut
from qr_chores.services.points import points_balance

router = APIRouter(tags=["api-auth"])


async def _user_out(db: AsyncSession, user: User) -> UserOut:
    balance = await points_balance(db, user.id)
    return UserOut(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        display_name=user.display_name,
        role=user.role.value,
        parent_id=user.parent_id,
        is_active=user.is_active,
        points_balance=balance,
    )


def _set_session_cookie(
    response: Response, settings: Settings, user_id: int, request: Request | None = None
) -> None:
    is_https = (
        request
        and (request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https")
    ) or settings.base_url.startswith("https://")
    response.set_cookie(
        key=settings.session_cookie_name,
        value=dump_session(settings, user_id),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=bool(is_https),
        path="/",
    )


@router.post("/auth/login", response_model=TokenResponse)
async def api_login(
    body: LoginRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    result = await db.execute(
        select(User).where(User.email == body.email.strip().lower(), User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        log_user_action("login_failed", detail="api", email=body.email.strip().lower())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = dump_api_token(settings, user.id)
    _set_session_cookie(response, settings, user.id, request=request)
    log_user_action("login", user_id=user.id, detail="api", role=user.role.value)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.session_max_age_seconds,
        user=await _user_out(db, user),
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def api_logout(
    response: Response,
    user: User | None = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings),
) -> None:
    """Clear session cookie. Bearer tokens are discarded client-side."""
    log_user_action("logout", user_id=user.id if user else None, detail="api")
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=UserOut)
async def api_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    return await _user_out(db, user)
