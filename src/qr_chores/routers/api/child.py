"""Child-facing API: home, confirm, complete, achievements."""

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from qr_chores.auth.deps import require_role
from qr_chores.config import Settings, get_settings
from qr_chores.db import get_db
from qr_chores.models.chore import Chore
from qr_chores.models.rewards import Achievement, UserAchievement
from qr_chores.models.user import User, UserRole
from qr_chores.routers.api.serializers import (
    board_item,
    chore_summary,
    completion_summary,
    is_late_pending_for_chore,
    unlock_from_achievement,
    unlock_from_user_achievement,
)
from qr_chores.schemas.chores import (
    AchievementProgressOut,
    AchievementsResponse,
    ChoreConfirmOut,
    CompleteResponse,
    HomeResponse,
    PointsBreakdownOut,
)
from qr_chores.services.achievements import progress_for
from qr_chores.services.chores import today_board
from qr_chores.services.completion import (
    CompletionError,
    complete_chore,
    get_completion_for_today,
)
from qr_chores.services.points import points_balance
from qr_chores.services.timeutil import is_scheduled_on, local_now, local_today
from qr_chores.services.uploads import read_photo_upload

router = APIRouter(tags=["api-child"])


async def _load_chore_by_token(db: AsyncSession, token: str) -> Chore | None:
    result = await db.execute(select(Chore).where(Chore.qr_token == token))
    return result.scalar_one_or_none()


def _completion_http_error(exc: CompletionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"message": exc.message, "code": exc.code},
    )


@router.get("/home", response_model=HomeResponse)
async def api_home(
    user: User = Depends(require_role(UserRole.child)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HomeResponse:
    board = await today_board(db, settings)
    points_today = sum((row.completion.points_awarded if row.completion else 0) for row in board)
    done_count = sum(1 for row in board if row.done)
    balance = await points_balance(db, user.id)
    result = await db.execute(
        select(UserAchievement)
        .options(selectinload(UserAchievement.achievement))
        .where(UserAchievement.user_id == user.id)
        .order_by(UserAchievement.unlocked_at.desc())
        .limit(3)
    )
    recent = list(result.scalars().all())
    return HomeResponse(
        local_date=local_today(settings),
        points_balance=balance,
        points_today=points_today,
        done_count=done_count,
        total_count=len(board),
        board=[board_item(row) for row in board],
        recent_unlocks=[unlock_from_user_achievement(ua) for ua in recent],
    )


@router.get("/c/{qr_token}", response_model=ChoreConfirmOut)
async def api_confirm_chore(
    qr_token: str,
    user: User = Depends(require_role(UserRole.child)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChoreConfirmOut:
    del user  # role gate only
    chore = await _load_chore_by_token(db, qr_token)
    if chore is None or not chore.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chore not found")

    today = local_today(settings)
    scheduled = is_scheduled_on(chore.schedule_days, today)
    completion = await get_completion_for_today(db, chore, settings)
    now = local_now(settings)
    late = is_late_pending_for_chore(
        chore=chore,
        completion=completion,
        scheduled=scheduled,
        now=now,
        today=today,
        grace_minutes=settings.on_time_grace_minutes,
    )
    return ChoreConfirmOut(
        chore=chore_summary(chore),
        scheduled_today=scheduled,
        already_done=completion is not None,
        is_late_pending=late,
        completion=completion_summary(completion) if completion else None,
    )


@router.post("/c/{qr_token}/complete", response_model=CompleteResponse)
async def api_complete_chore(
    qr_token: str,
    user: User = Depends(require_role(UserRole.child)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    photo: UploadFile | None = File(None),
) -> CompleteResponse:
    chore = await _load_chore_by_token(db, qr_token)
    if chore is None or not chore.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chore not found")

    try:
        photo_upload = await read_photo_upload(photo, max_bytes=settings.photo_max_bytes)
        result = await complete_chore(
            db,
            chore=chore,
            user=user,
            settings=settings,
            photo=photo_upload,
        )
    except CompletionError as exc:
        raise _completion_http_error(exc) from exc

    points = PointsBreakdownOut(
        base=result.points.base,
        timing_bonus=result.points.timing_bonus,
        achievement_points=result.points.achievement_points,
        total=result.points.total,
    )
    if result.already_done:
        # Already-done path has empty PointsBreakdown; surface completion totals.
        points = PointsBreakdownOut(
            base=result.completion.points_awarded,
            timing_bonus=0,
            achievement_points=0,
            total=result.completion.points_awarded,
        )

    unlocks = [unlock_from_achievement(u.achievement) for u in result.unlocks]
    return CompleteResponse(
        already_done=result.already_done,
        chore=chore_summary(result.chore),
        completion=completion_summary(result.completion),
        points=points,
        unlocks=unlocks,
    )


@router.get("/achievements", response_model=AchievementsResponse)
async def api_achievements(
    user: User = Depends(require_role(UserRole.child)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AchievementsResponse:
    result = await db.execute(
        select(Achievement).where(Achievement.is_active.is_(True)).order_by(Achievement.title)
    )
    achievements = list(result.scalars().all())
    owned = await db.execute(
        select(UserAchievement.achievement_id).where(UserAchievement.user_id == user.id)
    )
    owned_ids = set(owned.scalars().all())

    rows: list[AchievementProgressOut] = []
    for ach in achievements:
        try:
            data = json.loads(ach.criteria_json or "{}")
        except json.JSONDecodeError:
            data = {}
        threshold = int(data.get("count", data.get("days", 1)))
        progress = await progress_for(db, user.id, ach, settings)
        unlocked = ach.id in owned_ids
        capped = threshold if unlocked else min(progress, threshold)
        percent = 100 if threshold <= 0 else min(100, int(100 * capped / threshold))
        rows.append(
            AchievementProgressOut(
                id=ach.id,
                title=ach.title,
                description=ach.description,
                icon_key=ach.icon_key,
                criteria_type=ach.criteria_type.value,
                points_reward=ach.points_reward,
                unlocked=unlocked,
                progress=capped,
                threshold=threshold,
                percent=percent,
            )
        )
    rows.sort(key=lambda r: (not r.unlocked, r.title))
    balance = await points_balance(db, user.id)
    return AchievementsResponse(
        points_balance=balance,
        unlocked_count=sum(1 for r in rows if r.unlocked),
        achievements=rows,
    )
