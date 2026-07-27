"""Admin API: bootstrap user registration (API key)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import require_admin_api_key
from qr_chores.db import get_db
from qr_chores.models.user import UserRole
from qr_chores.routers.api.auth import _user_out
from qr_chores.schemas.auth import AdminRegisterRequest, UserOut
from qr_chores.services.users import UserServiceError, create_user

router = APIRouter(prefix="/admin", tags=["api-admin"])


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_api_key)],
)
async def admin_register_user(
    body: AdminRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Register a user (typically a parent) with username + password + name.

    Auth: ``X-Admin-Key: <ADMIN_API_KEY>``. No email format validation.
    """
    role_raw = (body.role or "parent").strip().lower()
    try:
        role = UserRole(role_raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="role must be 'parent' or 'child'",
        ) from exc

    try:
        user = await create_user(
            db,
            email=body.email,
            password=body.password,
            first_name=body.first_name,
            last_name=body.last_name,
            role=role,
            parent_id=body.parent_id if role == UserRole.child else None,
        )
        await db.commit()
        await db.refresh(user)
    except UserServiceError as exc:
        await db.rollback()
        code = (
            status.HTTP_409_CONFLICT
            if exc.code == "username_taken"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=code,
            detail={"message": exc.message, "code": exc.code},
        ) from exc

    return await _user_out(db, user)
