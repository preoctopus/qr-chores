"""Mark chores complete for a local day."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.config import Settings
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy, TimingStatus
from qr_chores.models.user import User
from qr_chores.services.achievements import UnlockedAchievement, evaluate_achievements
from qr_chores.services.points import add_ledger_entry, get_timing_bonuses
from qr_chores.services.storage import (
    StorageError,
    get_photo_storage,
    validate_and_build_key,
)
from qr_chores.services.timeutil import classify_timing, is_scheduled_on, local_now, local_today


class CompletionError(Exception):
    def __init__(self, message: str, code: str = "error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass
class PointsBreakdown:
    base: int = 0
    timing_bonus: int = 0
    achievement_points: int = 0

    @property
    def total(self) -> int:
        return self.base + self.timing_bonus + self.achievement_points


@dataclass
class CompletionResult:
    completion: ChoreCompletion
    chore: Chore
    already_done: bool = False
    points: PointsBreakdown = field(default_factory=PointsBreakdown)
    unlocks: list[UnlockedAchievement] = field(default_factory=list)


@dataclass
class PhotoUpload:
    data: bytes
    content_type: str | None


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


def _resolve_photo_key(
    *,
    chore: Chore,
    photo: PhotoUpload | None,
    settings: Settings,
    local_date_str: str,
) -> str | None:
    policy = chore.photo_policy
    has_photo = photo is not None and bool(photo.data)

    if policy == PhotoPolicy.none:
        return None

    if policy == PhotoPolicy.required and not has_photo:
        raise CompletionError("A photo is required for this chore.", "photo_required")

    if not has_photo:
        return None

    assert photo is not None
    try:
        key, content_type = validate_and_build_key(
            data=photo.data,
            declared_content_type=photo.content_type,
            chore_id=chore.id,
            local_date_str=local_date_str,
            settings=settings,
        )
        storage = get_photo_storage(settings)
        storage.save(key, photo.data, content_type)
        return key
    except StorageError as exc:
        raise CompletionError(exc.message, exc.code) from exc


def _timing_bonus_amount(timing: TimingStatus, bonuses: dict[str, int]) -> int:
    if timing == TimingStatus.early:
        return max(0, bonuses.get("early_bonus_points", 0))
    if timing == TimingStatus.on_time:
        return max(0, bonuses.get("on_time_bonus_points", 0))
    return max(0, bonuses.get("late_bonus_points", 0))


async def complete_chore(
    db: AsyncSession,
    *,
    chore: Chore,
    user: User,
    settings: Settings,
    photo: PhotoUpload | None = None,
) -> CompletionResult:
    if not chore.is_active:
        raise CompletionError("This chore is no longer active.", "inactive")

    today = local_today(settings)
    if not is_scheduled_on(chore.schedule_days, today):
        raise CompletionError("This chore is not scheduled for today.", "not_scheduled")

    existing = await get_completion_for_today(db, chore, settings)
    if existing is not None:
        return CompletionResult(completion=existing, chore=chore, already_done=True)

    photo_key = _resolve_photo_key(
        chore=chore,
        photo=photo,
        settings=settings,
        local_date_str=today.isoformat(),
    )

    now = local_now(settings)
    timing = classify_timing(
        completed_at=now,
        due_time=chore.due_time,
        local_date=today,
        settings=settings,
    )
    bonuses = await get_timing_bonuses(db)
    base = max(0, chore.base_points)
    timing_bonus = _timing_bonus_amount(timing, bonuses)
    points_awarded = base + timing_bonus

    completion = ChoreCompletion(
        chore_id=chore.id,
        user_id=user.id,
        local_date=today,
        completed_at=now,
        timing=timing,
        photo_object_key=photo_key,
        points_awarded=points_awarded,
    )
    db.add(completion)

    try:
        await db.flush()  # get completion.id for ledger refs
        add_ledger_entry(
            db,
            user_id=user.id,
            delta=base,
            reason=f"Completed: {chore.title}",
            ref_type="completion",
            ref_id=completion.id,
        )
        if timing_bonus:
            label = timing.value.replace("_", " ")
            add_ledger_entry(
                db,
                user_id=user.id,
                delta=timing_bonus,
                reason=f"Timing bonus ({label})",
                ref_type="completion_bonus",
                ref_id=completion.id,
            )

        unlocks = await evaluate_achievements(db, user_id=user.id, settings=settings)
        achievement_points = sum(u.points for u in unlocks)

        # Reflect achievement points on this completion display total
        completion.points_awarded = points_awarded + achievement_points

        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if photo_key:
            try:
                get_photo_storage(settings).delete(photo_key)
            except StorageError:
                pass
        existing = await get_completion_for_today(db, chore, settings)
        if existing is not None:
            return CompletionResult(completion=existing, chore=chore, already_done=True)
        raise CompletionError("Could not save completion.", "db") from exc

    await db.refresh(completion)
    return CompletionResult(
        completion=completion,
        chore=chore,
        already_done=False,
        points=PointsBreakdown(
            base=base,
            timing_bonus=timing_bonus,
            achievement_points=achievement_points,
        ),
        unlocks=unlocks,
    )
