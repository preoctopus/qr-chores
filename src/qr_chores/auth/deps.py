"""FastAPI auth dependencies."""

import hmac
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.session import load_api_token, load_session
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.models.user import User, UserRole


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if not auth:
        return None
    scheme, _, value = auth.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User | None:
    """Resolve user from Bearer token (preferred) or session cookie."""
    user_id: int | None = None
    bearer = _bearer_token(request)
    if bearer:
        # Prefer API salt; also accept session cookie value as Bearer for convenience.
        user_id = load_api_token(settings, bearer)
        if user_id is None:
            user_id = load_session(settings, bearer)
    else:
        cookie = request.cookies.get(settings.session_cookie_name)
        if cookie:
            user_id = load_session(settings, cookie)

    if user_id is None:
        return None
    result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    return result.scalar_one_or_none()


async def get_current_user(
    user: User | None = Depends(get_current_user_optional),
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(*roles: UserRole) -> Callable:
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _dep


def require_admin_api_key(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """Require ``X-Admin-Key`` matching ``ADMIN_API_KEY`` (constant-time)."""
    configured = (settings.admin_api_key or "").strip()
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is not configured (set ADMIN_API_KEY).",
        )
    provided = (request.headers.get("X-Admin-Key") or "").strip()
    if not provided or not hmac.compare_digest(provided, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin API key.",
        )
