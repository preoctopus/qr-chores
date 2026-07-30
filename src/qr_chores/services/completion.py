"""Mark chores complete for a local day."""

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
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
    chore: Chore | int,
    settings: Settings,
) -> ChoreCompletion | None:
    """Return today's completion for a chore (by model or id).

    Accepts ``chore_id`` as int so callers can recover after ``session.rollback()``
    without touching an expired ORM instance.
    """
    today = local_today(settings)
    chore_id = chore if isinstance(chore, int) else chore.id
    result = await db.execute(
        select(ChoreCompletion).where(
            ChoreCompletion.chore_id == chore_id,
            ChoreCompletion.local_date == today,
        )
    )
    return result.scalar_one_or_none()


async def open_completion_photo(
    db: AsyncSession,
    settings: Settings,
    completion_id: int,
) -> tuple[bytes, str]:
    """Return ``(bytes, content_type)`` for a completion photo.

    Raises :class:`StorageError` with ``code="not_found"`` when the completion
    or photo is missing; other storage failures re-raise as :class:`StorageError`.
    """
    result = await db.execute(select(ChoreCompletion).where(ChoreCompletion.id == completion_id))
    completion = result.scalar_one_or_none()
    if completion is None or not completion.photo_object_key:
        raise StorageError("Photo not found", code="not_found")
    return get_photo_storage(settings).open(completion.photo_object_key)


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


def _timing_bonus_amount(
    timing: TimingStatus, bonuses: dict[str, int], *, early_bonus_enabled: bool = True
) -> int:
    """Return timing bonus points for a completion status.

    Early and on-time bonuses are clamped to non-negative values. Late may be
    negative so parents can configure a late *penalty* (e.g. -2 points).
    If early_bonus_enabled is False, completing early awards 0 bonus points.
    """
    if timing == TimingStatus.early:
        if not early_bonus_enabled:
            return 0
        return max(0, bonuses.get("early_bonus_points", 0))
    if timing == TimingStatus.on_time:
        return max(0, bonuses.get("on_time_bonus_points", 0))
    # Late bonus intentionally allows negatives (penalty). Zero skips ledger row.
    return int(bonuses.get("late_bonus_points", 0))


async def complete_chore(
    db: AsyncSession,
    *,
    chore: Chore,
    user: User,
    settings: Settings,
    photo: PhotoUpload | None = None,
    notes: str | None = None,
) -> CompletionResult:
    if not chore.is_active:
        raise CompletionError("This chore is no longer active.", "inactive")

    # Chores belong to one child; siblings (or wrong accounts) cannot complete them.
    if chore.assignee_user_id is not None and chore.assignee_user_id != user.id:
        raise CompletionError(
            "This chore is assigned to someone else.",
            "wrong_assignee",
        )

    clean_notes = notes.strip() if notes and notes.strip() else None

    # Capture primitives before the write transaction: after IntegrityError +
    # rollback, ORM instances may be expired and unsafe to attribute-load.
    chore_id = chore.id
    chore_title = chore.title
    schedule_days = chore.schedule_days
    due_time = chore.due_time
    base = max(0, chore.base_points)
    early_bonus_enabled = chore.early_bonus_enabled

    today = local_today(settings)
    if not is_scheduled_on(schedule_days, today):
        raise CompletionError("This chore is not scheduled for today.", "not_scheduled")

    existing = await get_completion_for_today(db, chore_id, settings)
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
        due_time=due_time,
        local_date=today,
        settings=settings,
    )
    bonuses = await get_timing_bonuses(db)
    timing_bonus = _timing_bonus_amount(timing, bonuses, early_bonus_enabled=early_bonus_enabled)
    points_awarded = base + timing_bonus

    completion = ChoreCompletion(
        chore_id=chore_id,
        user_id=user.id,
        local_date=today,
        completed_at=now,
        timing=timing,
        photo_object_key=photo_key,
        had_photo=bool(photo_key),
        notes=clean_notes,
        points_awarded=points_awarded,
    )
    db.add(completion)

    try:
        await db.flush()  # get completion.id for ledger refs
        add_ledger_entry(
            db,
            user_id=user.id,
            delta=base,
            reason=f"Completed: {chore_title}",
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

        # Keep points_awarded as base + timing only. Achievement rewards live in
        # PointLedger (and CompletionResult.points / celebration UI) so summing
        # completions never double-counts ledger achievement entries (#10).

        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if photo_key:
            from contextlib import suppress

            with suppress(StorageError):
                get_photo_storage(settings).delete(photo_key)
        existing = await get_completion_for_today(db, chore_id, settings)
        if existing is not None:
            # Re-load chore so the result is not bound to an expired instance.
            reloaded = await db.get(Chore, chore_id)
            return CompletionResult(
                completion=existing,
                chore=reloaded or chore,
                already_done=True,
            )
        raise CompletionError("Could not save completion.", "db") from exc

    if clean_notes:
        from qr_chores.services.email import send_completion_note_email

        await send_completion_note_email(
            db=db,
            settings=settings,
            completion=completion,
            chore=chore,
            child=user,
            notes=clean_notes,
        )

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


@dataclass
class HistoryStats:
    total_completions: int = 0
    completions_this_week: int = 0
    on_time_count: int = 0
    on_time_rate: float = 0.0
    total_points: int = 0
    current_streak: int = 0


@dataclass
class HistoryPagination:
    page: int = 1
    limit: int = 50
    total_count: int = 0
    total_pages: int = 0
    has_next: bool = False
    has_prev: bool = False


@dataclass
class ParentHistoryResult:
    completions: list[ChoreCompletion]
    stats: HistoryStats
    pagination: HistoryPagination


async def get_parent_history(
    db: AsyncSession,
    settings: Settings,
    parent_id: int,
    *,
    child_id: int | None = None,
    chore_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timing: TimingStatus | str | None = None,
    page: int = 1,
    limit: int = 50,
) -> ParentHistoryResult:
    """Fetch paginated, filtered completion history and stats for a parent's children."""
    import math

    from sqlalchemy.orm import selectinload

    from qr_chores.models.user import UserRole

    if isinstance(timing, str):
        try:
            timing = TimingStatus(timing)
        except ValueError:
            timing = None

    # Child IDs belonging to parent
    child_ids_subquery = select(User.id).where(
        User.role == UserRole.child,
        User.parent_id == parent_id,
    )

    base_where = [ChoreCompletion.user_id.in_(child_ids_subquery)]
    if child_id is not None:
        base_where.append(ChoreCompletion.user_id == child_id)
    if chore_id is not None:
        base_where.append(ChoreCompletion.chore_id == chore_id)
    if start_date is not None:
        base_where.append(ChoreCompletion.local_date >= start_date)
    if end_date is not None:
        base_where.append(ChoreCompletion.local_date <= end_date)
    if timing is not None:
        base_where.append(ChoreCompletion.timing == timing)

    # 1. Total count
    count_q = select(func.count()).select_from(ChoreCompletion).where(*base_where)
    total_count = int(await db.scalar(count_q) or 0)

    # 2. Paginated completions
    limit = max(1, min(limit, 200))
    page = max(1, page)
    total_pages = math.ceil(total_count / limit) if total_count > 0 else 1
    page = min(page, total_pages)
    offset = (page - 1) * limit

    list_q = (
        select(ChoreCompletion)
        .options(
            selectinload(ChoreCompletion.chore),
            selectinload(ChoreCompletion.user),
        )
        .where(*base_where)
        .order_by(ChoreCompletion.completed_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(list_q)
    completions = list(result.scalars().all())

    # 3. Summary stats
    today = local_today(settings)
    week_start = today - timedelta(days=6)

    # Completions this week count
    this_week_q = (
        select(func.count())
        .select_from(ChoreCompletion)
        .where(
            *base_where,
            ChoreCompletion.local_date >= week_start,
        )
    )
    completions_this_week = int(await db.scalar(this_week_q) or 0)

    # On-time count (on_time or early)
    on_time_q = (
        select(func.count())
        .select_from(ChoreCompletion)
        .where(
            *base_where,
            ChoreCompletion.timing.in_([TimingStatus.on_time, TimingStatus.early]),
        )
    )
    on_time_count = int(await db.scalar(on_time_q) or 0)
    on_time_rate = round((on_time_count / total_count) * 100, 1) if total_count > 0 else 0.0

    # Total points awarded
    points_q = select(func.sum(ChoreCompletion.points_awarded)).where(*base_where)
    total_points = int(await db.scalar(points_q) or 0)

    # Current streak calculation across scope
    dates_q = select(ChoreCompletion.local_date).where(*base_where).distinct()
    dates_res = await db.execute(dates_q)
    days = {row[0] for row in dates_res.all()}
    streak = 0
    if days:
        cursor = today if today in days else today - timedelta(days=1)
        while cursor in days:
            streak += 1
            cursor = cursor - timedelta(days=1)

    stats = HistoryStats(
        total_completions=total_count,
        completions_this_week=completions_this_week,
        on_time_count=on_time_count,
        on_time_rate=on_time_rate,
        total_points=total_points,
        current_streak=streak,
    )

    pagination = HistoryPagination(
        page=page,
        limit=limit,
        total_count=total_count,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

    return ParentHistoryResult(
        completions=completions,
        stats=stats,
        pagination=pagination,
    )
