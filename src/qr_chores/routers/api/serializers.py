"""Map domain objects to API response schemas."""

from datetime import date, datetime, timedelta

from qr_chores.models.chore import Chore, ChoreCompletion
from qr_chores.models.rewards import Achievement, UserAchievement
from qr_chores.schemas.chores import (
    BoardItemOut,
    ChoreSummaryOut,
    CompletionSummaryOut,
    UnlockOut,
)
from qr_chores.services.chores import ChoreDayStatus


def chore_summary(chore: Chore) -> ChoreSummaryOut:
    return ChoreSummaryOut(
        id=chore.id,
        title=chore.title,
        description=chore.description,
        qr_token=chore.qr_token,
        due_time=chore.due_time,
        schedule_days=chore.schedule_days,
        photo_policy=chore.photo_policy.value,
        base_points=chore.base_points,
        is_active=chore.is_active,
    )


def completion_summary(completion: ChoreCompletion) -> CompletionSummaryOut:
    return CompletionSummaryOut(
        id=completion.id,
        local_date=completion.local_date,
        completed_at=completion.completed_at,
        timing=completion.timing.value,
        points_awarded=completion.points_awarded,
        has_photo=bool(completion.photo_object_key),
    )


def board_item(row: ChoreDayStatus) -> BoardItemOut:
    return BoardItemOut(
        chore=chore_summary(row.chore),
        done=row.done,
        status_label=row.status_label,
        status_kind=row.status_kind,
        is_late_pending=row.is_late_pending,
        timing=row.timing.value if row.timing else None,
        completion=completion_summary(row.completion) if row.completion else None,
    )


def unlock_from_user_achievement(ua: UserAchievement) -> UnlockOut:
    ach = ua.achievement
    return UnlockOut(
        id=ach.id,
        title=ach.title,
        description=ach.description,
        icon_key=ach.icon_key,
        points_reward=ach.points_reward,
        unlocked_at=ua.unlocked_at,
    )


def unlock_from_achievement(
    achievement: Achievement,
    *,
    unlocked_at: datetime | None = None,
) -> UnlockOut:
    return UnlockOut(
        id=achievement.id,
        title=achievement.title,
        description=achievement.description,
        icon_key=achievement.icon_key,
        points_reward=achievement.points_reward,
        unlocked_at=unlocked_at,
    )


def is_late_pending_for_chore(
    *,
    chore: Chore,
    completion: ChoreCompletion | None,
    scheduled: bool,
    now: datetime,
    today: date,
    grace_minutes: int,
) -> bool:
    if not scheduled or completion is not None:
        return False
    due_dt = datetime.combine(today, chore.due_time, tzinfo=now.tzinfo)
    return now > due_dt + timedelta(minutes=grace_minutes)
