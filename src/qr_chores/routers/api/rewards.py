"""Parent rewards admin API: timing bonuses + achievements."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.deps import require_role
from qr_chores.db import get_db
from qr_chores.models.rewards import Achievement, CriteriaType
from qr_chores.models.user import User, UserRole
from qr_chores.schemas.rewards import (
    AchievementAdminOut,
    AchievementCreate,
    AchievementUpdate,
    RewardsResponse,
    TimingBonusesOut,
    TimingBonusesUpdate,
)
from qr_chores.services.achievements import criteria_threshold, ensure_default_achievements
from qr_chores.services.points import DEFAULT_BONUSES, get_timing_bonuses, set_setting

router = APIRouter(tags=["api-rewards"])


def _criteria_json(criteria_type: CriteriaType, threshold: int) -> str:
    if criteria_type == CriteriaType.streak_days:
        return json.dumps({"days": threshold})
    return json.dumps({"count": threshold})


def _achievement_out(ach: Achievement) -> AchievementAdminOut:
    return AchievementAdminOut(
        id=ach.id,
        title=ach.title,
        description=ach.description,
        icon_key=ach.icon_key,
        criteria_type=ach.criteria_type.value,
        threshold=criteria_threshold(ach),
        points_reward=ach.points_reward,
        is_active=ach.is_active,
    )


@router.get("/rewards", response_model=RewardsResponse)
async def api_rewards(
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> RewardsResponse:
    del user
    await ensure_default_achievements(db)
    await db.commit()
    bonuses = await get_timing_bonuses(db)
    result = await db.execute(
        select(Achievement).order_by(Achievement.is_active.desc(), Achievement.title)
    )
    achievements = list(result.scalars().all())
    return RewardsResponse(
        bonuses=TimingBonusesOut(
            early_bonus_points=bonuses["early_bonus_points"],
            on_time_bonus_points=bonuses["on_time_bonus_points"],
            late_bonus_points=bonuses["late_bonus_points"],
        ),
        achievements=[_achievement_out(a) for a in achievements],
    )


@router.put("/rewards/bonuses", response_model=TimingBonusesOut)
async def api_update_bonuses(
    body: TimingBonusesUpdate,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> TimingBonusesOut:
    del user
    values = {
        "early_bonus_points": body.early_bonus_points,
        "on_time_bonus_points": body.on_time_bonus_points,
        "late_bonus_points": body.late_bonus_points,
    }
    for key in DEFAULT_BONUSES:
        await set_setting(db, key, str(values[key]))
    await db.commit()
    return TimingBonusesOut(**values)


@router.post(
    "/rewards/achievements",
    response_model=AchievementAdminOut,
    status_code=status.HTTP_201_CREATED,
)
async def api_create_achievement(
    body: AchievementCreate,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> AchievementAdminOut:
    del user
    criteria_type = CriteriaType(body.criteria_type)
    ach = Achievement(
        title=body.title,
        description=body.description,
        icon_key=body.icon_key,
        criteria_type=criteria_type,
        criteria_json=_criteria_json(criteria_type, body.threshold),
        points_reward=body.points_reward,
        is_active=True,
    )
    db.add(ach)
    await db.commit()
    await db.refresh(ach)
    return _achievement_out(ach)


@router.patch("/rewards/achievements/{achievement_id}", response_model=AchievementAdminOut)
async def api_update_achievement(
    achievement_id: int,
    body: AchievementUpdate,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> AchievementAdminOut:
    del user
    ach = await db.get(Achievement, achievement_id)
    if ach is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Achievement not found")

    if body.title is not None:
        ach.title = body.title
    if body.description is not None:
        ach.description = body.description.strip()
    if body.icon_key is not None:
        ach.icon_key = body.icon_key.strip() or "star"
    if body.criteria_type is not None:
        ach.criteria_type = CriteriaType(body.criteria_type)
    if body.threshold is not None or body.criteria_type is not None:
        threshold = body.threshold if body.threshold is not None else criteria_threshold(ach)
        ach.criteria_json = _criteria_json(ach.criteria_type, threshold)
    if body.points_reward is not None:
        ach.points_reward = body.points_reward

    await db.commit()
    await db.refresh(ach)
    return _achievement_out(ach)


@router.post("/rewards/achievements/{achievement_id}/toggle", response_model=AchievementAdminOut)
async def api_toggle_achievement(
    achievement_id: int,
    user: User = Depends(require_role(UserRole.parent)),
    db: AsyncSession = Depends(get_db),
) -> AchievementAdminOut:
    del user
    ach = await db.get(Achievement, achievement_id)
    if ach is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Achievement not found")
    ach.is_active = not ach.is_active
    await db.commit()
    await db.refresh(ach)
    return _achievement_out(ach)
