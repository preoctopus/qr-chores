"""Parent-facing API: today board, history, chore CRUD, QR."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from qr_chores.auth.deps import require_role
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy
from qr_chores.models.user import User, UserRole
from qr_chores.routers.api.serializers import board_item, chore_summary, completion_summary
from qr_chores.schemas.chores import ChoreSummaryOut
from qr_chores.schemas.parent import (
    ChoreCreate,
    ChoreDeleteResponse,
    ChoreListResponse,
    ChoreUpdate,
    HistoryItemOut,
    HistoryResponse,
    QrInfoOut,
    TodayResponse,
)
from qr_chores.services.chores import (
    delete_chore,
    list_all_chores,
    today_board,
)
from qr_chores.services.qr import chore_url, generate_qr_png, new_qr_token
from qr_chores.services.timeutil import local_today

router = APIRouter(tags=["api-parent"])


@router.get("/today", response_model=TodayResponse)
async def api_today(
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TodayResponse:
    del user  # role gate only
    board = await today_board(db, settings)
    return TodayResponse(
        local_date=local_today(settings),
        board=[board_item(row) for row in board],
    )


@router.get("/history", response_model=HistoryResponse)
async def api_history(
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
) -> HistoryResponse:
    del user
    result = await db.execute(
        select(ChoreCompletion)
        .options(selectinload(ChoreCompletion.chore))
        .order_by(ChoreCompletion.completed_at.desc())
        .limit(limit)
    )
    completions = list(result.scalars().all())
    items = [
        HistoryItemOut(
            completion=completion_summary(row),
            chore_id=row.chore_id,
            chore_title=row.chore.title if row.chore is not None else "",
            user_id=row.user_id,
        )
        for row in completions
    ]
    return HistoryResponse(items=items, limit=limit)


@router.get("/chores", response_model=ChoreListResponse)
async def api_list_chores(
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    include_inactive: bool = Query(True),
) -> ChoreListResponse:
    del user
    chores = await list_all_chores(db, include_inactive=include_inactive)
    return ChoreListResponse(chores=[chore_summary(c) for c in chores])


@router.post("/chores", response_model=ChoreSummaryOut, status_code=status.HTTP_201_CREATED)
async def api_create_chore(
    body: ChoreCreate,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> ChoreSummaryOut:
    del user
    chore = Chore(
        title=body.title,
        description=body.description,
        qr_token=new_qr_token(),
        due_time=body.due_time,
        schedule_days=body.schedule_days,
        photo_policy=PhotoPolicy(body.photo_policy),
        base_points=body.base_points,
        is_active=True,
    )
    db.add(chore)
    await db.commit()
    await db.refresh(chore)
    return chore_summary(chore)


@router.get("/chores/{chore_id}", response_model=ChoreSummaryOut)
async def api_get_chore(
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> ChoreSummaryOut:
    del user
    chore = await db.get(Chore, chore_id)
    if chore is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chore not found")
    return chore_summary(chore)


@router.patch("/chores/{chore_id}", response_model=ChoreSummaryOut)
async def api_update_chore(
    chore_id: int,
    body: ChoreUpdate,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> ChoreSummaryOut:
    del user
    chore = await db.get(Chore, chore_id)
    if chore is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chore not found")

    if body.title is not None:
        chore.title = body.title
    if body.clear_description:
        chore.description = None
    elif body.description is not None:
        stripped = body.description.strip()
        chore.description = stripped or None
    if body.due_time is not None:
        chore.due_time = body.due_time
    if body.schedule_days is not None:
        chore.schedule_days = body.schedule_days
    if body.photo_policy is not None:
        chore.photo_policy = PhotoPolicy(body.photo_policy)
    if body.base_points is not None:
        chore.base_points = body.base_points

    await db.commit()
    await db.refresh(chore)
    return chore_summary(chore)


@router.post("/chores/{chore_id}/deactivate", response_model=ChoreSummaryOut)
async def api_deactivate_chore(
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> ChoreSummaryOut:
    del user
    chore = await db.get(Chore, chore_id)
    if chore is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chore not found")
    chore.is_active = False
    await db.commit()
    await db.refresh(chore)
    return chore_summary(chore)


@router.post("/chores/{chore_id}/activate", response_model=ChoreSummaryOut)
async def api_activate_chore(
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> ChoreSummaryOut:
    del user
    chore = await db.get(Chore, chore_id)
    if chore is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chore not found")
    chore.is_active = True
    await db.commit()
    await db.refresh(chore)
    return chore_summary(chore)


@router.delete("/chores/{chore_id}", response_model=ChoreDeleteResponse)
async def api_delete_chore(
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChoreDeleteResponse:
    del user
    chore = await db.get(Chore, chore_id)
    if chore is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chore not found")
    removed = await delete_chore(db, chore, settings=settings)
    return ChoreDeleteResponse(deleted=True, chore_id=chore_id, completions_removed=removed)


@router.get("/chores/{chore_id}/qr", response_model=QrInfoOut)
async def api_chore_qr(
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> QrInfoOut:
    del user
    chore = await db.get(Chore, chore_id)
    if chore is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chore not found")
    return QrInfoOut(
        chore_id=chore.id,
        title=chore.title,
        qr_token=chore.qr_token,
        qr_url=chore_url(settings, chore.qr_token),
        png_path=f"/api/v1/chores/{chore.id}/qr.png",
    )


@router.get("/chores/{chore_id}/qr.png")
async def api_chore_qr_png(
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    del user
    chore = await db.get(Chore, chore_id)
    if chore is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chore not found")
    png = generate_qr_png(chore_url(settings, chore.qr_token))
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="chore-{chore.id}-qr.png"',
            "Cache-Control": "private, max-age=3600",
        },
    )
