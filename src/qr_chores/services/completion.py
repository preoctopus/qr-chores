"""Mark chores complete for a local day."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.config import Settings
from qr_chores.models.chore import Chore, ChoreCompletion, TimingStatus
from qr_chores.models.user import User
from qr_chores.services.timeutil import classify_timing, is_scheduled_on, local_now, local_today


class CompletionError(Exception):
    def __init__(self, message: str, code: str = "error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass
class CompletionResult:
    completion: ChoreCompletion
    chore: Chore
    already_done: bool = False


async def get_completion_for_today(
    db: AsyncSession,
    chore: Chore,
    settings: Settings,
) -> ChoreCompletion | None:
    today = local_today(settings)
    result = await db.execute(
        select(ChoreCompletion).where(
            ChoreCompletion.chore_id == chore.id,
            ChoreCompletion.local_date == today,
        )
    )
    return result.scalar_one_or_none()


async def complete_chore(
    db: AsyncSession,
    *,
    chore: Chore,
    user: User,
    settings: Settings,
) -> CompletionResult:
    if not chore.is_active:
        raise CompletionError("This chore is no longer active.", "inactive")

    today = local_today(settings)
    if not is_scheduled_on(chore.schedule_days, today):
        raise CompletionError("This chore is not scheduled for today.", "not_scheduled")

    existing = await get_completion_for_today(db, chore, settings)
    if existing is not None:
        return CompletionResult(completion=existing, chore=chore, already_done=True)

    now = local_now(settings)
    timing = classify_timing(
        completed_at=now,
        due_time=chore.due_time,
        local_date=today,
        settings=settings,
    )
    completion = ChoreCompletion(
        chore_id=chore.id,
        user_id=user.id,
        local_date=today,
        completed_at=now,
        timing=timing,
        photo_object_key=None,
        points_awarded=chore.base_points,
    )
    db.add(completion)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        existing = await get_completion_for_today(db, chore, settings)
        if existing is not None:
            return CompletionResult(completion=existing, chore=chore, already_done=True)
        raise CompletionError("Could not save completion.", "db") from exc

    await db.refresh(completion)
    return CompletionResult(completion=completion, chore=chore, already_done=False)
