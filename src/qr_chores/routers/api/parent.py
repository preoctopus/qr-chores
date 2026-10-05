"""Parent-facing API: today board, history, chore CRUD, QR."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import require_role
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.models.user import User, UserRole
from qr_chores.routers.api.serializers import board_item, chore_summary, completion_summary
from qr_chores.schemas.chores import ChoreSummaryOut
from qr_chores.schemas.parent import (
    ChildDayGroupOut,
    ChoreCreate,
    ChoreDeleteResponse,
    ChoreListResponse,
    ChoreUpdate,
    HistoryDayOut,
    HistoryDaysResponse,
    HistoryItemOut,
    HistoryPaginationOut,
    HistoryResponse,
    HistoryStatsOut,
    MissedChoreOut,
    QrInfoOut,
    TodayResponse,
    TodaySummaryOut,
    UndoCompletionResponse,
)
from qr_chores.services.chores import (
    delete_chore,
    list_all_chores,
)
from qr_chores.services.completion import get_parent_history
from qr_chores.services.dashboard import (
    ChildNotManagedError,
    build_today_dashboard,
    get_history_days,
)
from qr_chores.services.qr import chore_url, generate_qr_png, new_qr_token

router = APIRouter(tags=["api-parent"])


@router.get("/today", response_model=TodayResponse)
async def api_today(
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    child_id: int | None = Query(None, description="Filter board to one of your children"),
) -> TodayResponse:
    try:
        dash = await build_today_dashboard(db, settings, parent_id=user.id, child_id=child_id)
    except ChildNotManagedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Child not found"
        ) from exc
    s = dash.summary
    return TodayResponse(
        local_date=dash.local_date,
        board=[board_item(row) for row in dash.board],
        summary=TodaySummaryOut(
            total=s.total,
            done=s.done,
            pending=s.pending,
            overdue=s.overdue,
            done_late=s.done_late,
            points_today=s.points_today,
        ),
        children=[
            ChildDayGroupOut(
                child_id=g.child.id,
                child_name=g.name,
                done=g.done,
                total=g.total,
                overdue=g.overdue,
                points_today=g.points_today,
                items=[board_item(row) for row in g.rows],
            )
            for g in dash.groups
        ],
    )


@router.get("/history/days", response_model=HistoryDaysResponse)
async def api_history_days(
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    child_id: int | None = Query(None, description="Filter to child ID"),
    chore_id: int | None = Query(None, description="Filter to chore ID"),
    start_date: date | None = Query(None, description="Window start (default: 13 days before end)"),
    end_date: date | None = Query(None, description="Window end (default and max: today)"),
    timing: str | None = Query(None, description="Timing status; hides missed chores when set"),
) -> HistoryDaysResponse:
    res = await get_history_days(
        db,
        settings,
        parent_id=user.id,
        child_id=child_id,
        chore_id=chore_id,
        start_date=start_date,
        end_date=end_date,
        timing=timing,
    )
    return HistoryDaysResponse(
        start_date=res.start_date,
        end_date=res.end_date,
        older_start=res.older_start,
        older_end=res.older_end,
        newer_start=res.newer_start,
        newer_end=res.newer_end,
        days=[
            HistoryDayOut(
                local_date=d.local_date,
                scheduled=d.scheduled,
                done=d.done,
                missed_count=len(d.missed),
                open_count=d.open_count,
                points=d.points,
                completions=[
                    HistoryItemOut(
                        completion=completion_summary(c),
                        chore_id=c.chore_id,
                        chore_title=c.chore.title if c.chore is not None else "",
                        user_id=c.user_id,
                    )
                    for c in d.completions
                ],
                missed=[
                    MissedChoreOut(
                        chore_id=ch.id,
                        chore_title=ch.title,
                        user_id=ch.assignee_user_id,
                        due_time=ch.due_time,
                    )
                    for ch in d.missed
                ],
            )
            for d in res.days
        ],
    )


@router.get("/history", response_model=HistoryResponse)
async def api_history(
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    child_id: int | None = Query(None, description="Filter to child ID"),
    chore_id: int | None = Query(None, description="Filter to chore ID"),
    start_date: date | None = Query(None, description="Start date (inclusive)"),
    end_date: date | None = Query(None, description="End date (inclusive)"),
    timing: str | None = Query(None, description="Timing status (early, on_time, late)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
) -> HistoryResponse:
    res = await get_parent_history(
        db,
        settings,
        parent_id=user.id,
        child_id=child_id,
        chore_id=chore_id,
        start_date=start_date,
        end_date=end_date,
        timing=timing,
        page=page,
        limit=limit,
    )
    items = [
        HistoryItemOut(
            completion=completion_summary(row),
            chore_id=row.chore_id,
            chore_title=row.chore.title if row.chore is not None else "",
            user_id=row.user_id,
        )
        for row in res.completions
    ]
    return HistoryResponse(
        items=items,
        limit=res.pagination.limit,
        stats=HistoryStatsOut(
            total_completions=res.stats.total_completions,
            completions_this_week=res.stats.completions_this_week,
            on_time_count=res.stats.on_time_count,
            on_time_rate=res.stats.on_time_rate,
            total_points=res.stats.total_points,
            current_streak=res.stats.current_streak,
        ),
        pagination=HistoryPaginationOut(
            page=res.pagination.page,
            limit=res.pagination.limit,
            total_count=res.pagination.total_count,
            total_pages=res.pagination.total_pages,
            has_next=res.pagination.has_next,
            has_prev=res.pagination.has_prev,
        ),
    )


@router.get("/chores", response_model=ChoreListResponse)
async def api_list_chores(
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    include_inactive: bool = Query(True),
    child_id: int | None = Query(None),
) -> ChoreListResponse:
    chores = await list_all_chores(
        db,
        include_inactive=include_inactive,
        parent_id=user.id,
        assignee_user_id=child_id,
    )
    return ChoreListResponse(chores=[chore_summary(c) for c in chores])


async def _require_own_child(
    db: AsyncSession,
    parent: User,
    child_id: int,
    *,
    allow_inactive: bool = False,
) -> User:
    from qr_chores.services.users import get_child_for_parent

    child = await get_child_for_parent(db, parent.id, child_id)
    if child is None or (not allow_inactive and not child.is_active):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Assignee must be one of your active children.",
                "code": "bad_assignee",
            },
        )
    return child


async def _get_parent_chore(db: AsyncSession, parent: User, chore_id: int) -> Chore:
    from qr_chores.services.users import get_child_for_parent

    chore = await db.get(Chore, chore_id)
    if chore is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chore not found")
    if chore.assignee_user_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chore not found")
    child = await get_child_for_parent(db, parent.id, chore.assignee_user_id)
    if child is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chore not found")
    return chore


@router.post("/chores", response_model=ChoreSummaryOut, status_code=status.HTTP_201_CREATED)
async def api_create_chore(
    body: ChoreCreate,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> ChoreSummaryOut:
    child = await _require_own_child(db, user, body.assignee_user_id)
    chore = Chore(
        title=body.title,
        description=body.description,
        qr_token=new_qr_token(),
        due_time=body.due_time,
        schedule_days=body.schedule_days,
        photo_policy=PhotoPolicy(body.photo_policy),
        base_points=body.base_points,
        early_bonus_enabled=body.early_bonus_enabled,
        is_active=True,
        assignee_user_id=child.id,
    )
    db.add(chore)
    await db.commit()
    await db.refresh(chore)
    # Ensure assignee relationship for response name.
    chore.assignee = child
    return chore_summary(chore)


@router.get("/chores/{chore_id}", response_model=ChoreSummaryOut)
async def api_get_chore(
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> ChoreSummaryOut:
    chore = await _get_parent_chore(db, user, chore_id)
    return chore_summary(chore)


@router.patch("/chores/{chore_id}", response_model=ChoreSummaryOut)
async def api_update_chore(
    chore_id: int,
    body: ChoreUpdate,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> ChoreSummaryOut:
    chore = await _get_parent_chore(db, user, chore_id)

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
    if body.early_bonus_enabled is not None:
        chore.early_bonus_enabled = body.early_bonus_enabled
    if body.assignee_user_id is not None:
        child = await _require_own_child(db, user, body.assignee_user_id)
        chore.assignee_user_id = child.id

    await db.commit()
    await db.refresh(chore)
    return chore_summary(chore)


@router.post("/chores/{chore_id}/deactivate", response_model=ChoreSummaryOut)
async def api_deactivate_chore(
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> ChoreSummaryOut:
    chore = await _get_parent_chore(db, user, chore_id)
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
    chore = await _get_parent_chore(db, user, chore_id)
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
    chore = await _get_parent_chore(db, user, chore_id)
    removed = await delete_chore(db, chore, settings=settings)
    return ChoreDeleteResponse(deleted=True, chore_id=chore_id, completions_removed=removed)


@router.get("/chores/{chore_id}/qr", response_model=QrInfoOut)
async def api_chore_qr(
    request: Request,
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> QrInfoOut:
    chore = await _get_parent_chore(db, user, chore_id)
    return QrInfoOut(
        chore_id=chore.id,
        title=chore.title,
        qr_token=chore.qr_token,
        qr_url=chore_url(settings, chore.qr_token, request=request),
        png_path=f"/api/v1/chores/{chore.id}/qr.png",
    )


@router.get("/chores/{chore_id}/qr.png")
async def api_chore_qr_png(
    request: Request,
    chore_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    chore = await _get_parent_chore(db, user, chore_id)
    png = generate_qr_png(chore_url(settings, chore.qr_token, request=request))
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="chore-{chore.id}-qr.png"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.post("/completions/{completion_id}/undo", response_model=UndoCompletionResponse)
async def api_undo_completion(
    completion_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UndoCompletionResponse:
    from qr_chores.services.completion import CompletionError, undo_completion

    try:
        res = await undo_completion(
            db,
            completion_id=completion_id,
            parent_id=user.id,
            settings=settings,
        )
        return UndoCompletionResponse(
            success=True,
            completion_id=res.completion_id,
            chore_id=res.chore_id,
            points_reverted=res.points_reverted,
        )
    except CompletionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if exc.code == "not_found"
            else status.HTTP_400_BAD_REQUEST,
            detail={"message": exc.message, "code": exc.code},
        ) from exc
