"""Parent API: manage child accounts."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import require_role
from qr_chores.db import get_db
from qr_chores.models.user import User, UserRole
from qr_chores.routers.api.auth import _user_out
from qr_chores.schemas.auth import (
    ChildCreateRequest,
    ChildListResponse,
    ChildUpdateRequest,
    UserOut,
)
from qr_chores.services.users import (
    UserServiceError,
    create_user,
    get_child_for_parent,
    list_children_for_parent,
    update_user_profile,
)

router = APIRouter(tags=["api-parent"])


def _service_http(exc: UserServiceError) -> HTTPException:
    code = status.HTTP_409_CONFLICT if exc.code == "username_taken" else status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail={"message": exc.message, "code": exc.code})


@router.get("/children", response_model=ChildListResponse)
async def api_list_children(
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    include_inactive: bool = Query(True),
) -> ChildListResponse:
    kids = await list_children_for_parent(db, user.id, include_inactive=include_inactive)
    return ChildListResponse(children=[await _user_out(db, k) for k in kids])


@router.post("/children", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def api_create_child(
    body: ChildCreateRequest,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    try:
        child = await create_user(
            db,
            email=body.email,
            password=body.password,
            first_name=body.first_name,
            last_name=body.last_name,
            role=UserRole.child,
            parent_id=user.id,
        )
        await db.commit()
        await db.refresh(child)
    except UserServiceError as exc:
        await db.rollback()
        raise _service_http(exc) from exc
    return await _user_out(db, child)


@router.get("/children/{child_id}", response_model=UserOut)
async def api_get_child(
    child_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    child = await get_child_for_parent(db, user.id, child_id)
    if child is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Child not found")
    return await _user_out(db, child)


@router.patch("/children/{child_id}", response_model=UserOut)
async def api_update_child(
    child_id: int,
    body: ChildUpdateRequest,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    child = await get_child_for_parent(db, user.id, child_id)
    if child is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Child not found")
    try:
        await update_user_profile(
            db,
            child,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            password=body.password,
            is_active=body.is_active,
        )
        await db.commit()
        await db.refresh(child)
    except UserServiceError as exc:
        await db.rollback()
        raise _service_http(exc) from exc
    return await _user_out(db, child)


@router.post("/children/{child_id}/deactivate", response_model=UserOut)
async def api_deactivate_child(
    child_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    child = await get_child_for_parent(db, user.id, child_id)
    if child is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Child not found")
    child.is_active = False
    await db.commit()
    await db.refresh(child)
    return await _user_out(db, child)


@router.post("/children/{child_id}/activate", response_model=UserOut)
async def api_activate_child(
    child_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    child = await get_child_for_parent(db, user.id, child_id)
    if child is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Child not found")
    child.is_active = True
    await db.commit()
    await db.refresh(child)
    return await _user_out(db, child)
