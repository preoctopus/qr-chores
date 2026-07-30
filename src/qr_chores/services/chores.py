"""Chore listing helpers for today boards."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from qr_chores.config import Settings
from qr_chores.models.chore import Chore, ChoreCompletion, TimingStatus
from qr_chores.services.timeutil import is_scheduled_on, local_now, local_today


@dataclass
class ChoreDayStatus:
    chore: Chore
    done: bool
    completion: ChoreCompletion | None
    timing: TimingStatus | None
    is_late_pending: bool  # not done and past due+grace

    @property
    def status_label(self) -> str:
        if self.done and self.timing == TimingStatus.late:
            return "Done · late"
        if self.done and self.timing == TimingStatus.early:
            return "Done · early"
        if self.done:
            return "Done"
        if self.is_late_pending:
            return "Late"
        return "Pending"

    @property
    def status_kind(self) -> str:
        if self.done:
            return "done"
        if self.is_late_pending:
            return "late"
        return "pending"


async def list_active_chores(
    db: AsyncSession,
    *,
    assignee_user_id: int | None = None,
) -> list[Chore]:
    q = (
        select(Chore)
        .options(selectinload(Chore.assignee))
        .where(Chore.is_active.is_(True))
        .order_by(Chore.due_time, Chore.title)
    )
    if assignee_user_id is not None:
        q = q.where(Chore.assignee_user_id == assignee_user_id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def list_all_chores(
    db: AsyncSession,
    *,
    include_inactive: bool = True,
    assignee_user_id: int | None = None,
    parent_id: int | None = None,
) -> list[Chore]:
    """List chores. When ``parent_id`` is set, only chores assigned to that parent's children."""
    from qr_chores.models.user import User, UserRole

    q = (
        select(Chore)
        .options(selectinload(Chore.assignee))
        .order_by(Chore.is_active.desc(), Chore.due_time, Chore.title)
    )
    if not include_inactive:
        q = q.where(Chore.is_active.is_(True))
    if assignee_user_id is not None:
        q = q.where(Chore.assignee_user_id == assignee_user_id)
    if parent_id is not None:
        child_ids = select(User.id).where(
            User.role == UserRole.child,
            User.parent_id == parent_id,
        )
        q = q.where(Chore.assignee_user_id.in_(child_ids))
    result = await db.execute(q)
    return list(result.scalars().all())


async def today_board(
    db: AsyncSession,
    settings: Settings,
    *,
    assignee_user_id: int | None = None,
    parent_id: int | None = None,
) -> list[ChoreDayStatus]:
    today = local_today(settings)
    now = local_now(settings)
    if parent_id is not None and assignee_user_id is None:
        chores = await list_all_chores(
            db,
            include_inactive=False,
            parent_id=parent_id,
        )
        chores = [c for c in chores if c.is_active]
    else:
        chores = await list_active_chores(db, assignee_user_id=assignee_user_id)
    scheduled = [c for c in chores if is_scheduled_on(c.schedule_days, today)]
    if not scheduled:
        return []

    ids = [c.id for c in scheduled]
    result = await db.execute(
        select(ChoreCompletion)
        .options(selectinload(ChoreCompletion.user))
        .where(
            ChoreCompletion.chore_id.in_(ids),
            ChoreCompletion.local_date == today,
        )
    )
    by_chore = {c.chore_id: c for c in result.scalars().all()}

    board: list[ChoreDayStatus] = []
    for chore in scheduled:
        completion = by_chore.get(chore.id)
        done = completion is not None
        late_pending = False
        if not done:
            due_dt = datetime.combine(today, chore.due_time, tzinfo=now.tzinfo)
            grace = timedelta(minutes=settings.on_time_grace_minutes)
            late_pending = now > due_dt + grace
        board.append(
            ChoreDayStatus(
                chore=chore,
                done=done,
                completion=completion,
                timing=completion.timing if completion else None,
                is_late_pending=late_pending,
            )
        )

    def sort_key(item: ChoreDayStatus) -> tuple[int, time, str]:
        if not item.done:
            rank = 0 if item.is_late_pending else 1
        else:
            if item.timing == TimingStatus.late:
                rank = 2  # Done Late
            elif item.timing == TimingStatus.early:
                rank = 3  # Done early
            else:
                rank = 4  # Done on time
        return (rank, item.chore.due_time, item.chore.title)

    board.sort(key=sort_key)
    return board


def parse_due_time(value: str) -> time:
    """Parse HTML time input HH:MM or HH:MM:SS."""
    value = value.strip()
    parts = value.split(":")
    if len(parts) < 2:
        raise ValueError("Invalid time")
    hour = int(parts[0])
    minute = int(parts[1])
    second = int(parts[2]) if len(parts) > 2 else 0
    return time(hour=hour, minute=minute, second=second)


def parse_schedule_days(form_days: list[str] | None) -> str:
    """Build schedule string from form weekday checkboxes (0-6)."""
    if not form_days:
        return "0123456"
    digits = sorted({d for d in form_days if d in "0123456"})
    if not digits:
        return "0123456"
    return "".join(digits)


DAY_LABELS = [
    ("0", "Mon"),
    ("1", "Tue"),
    ("2", "Wed"),
    ("3", "Thu"),
    ("4", "Fri"),
    ("5", "Sat"),
    ("6", "Sun"),
]


def schedule_labels(schedule_days: str) -> str:
    if schedule_days == "0123456":
        return "Every day"
    if schedule_days == "01234":
        return "Weekdays"
    if schedule_days == "56":
        return "Weekends"
    labels = [label for digit, label in DAY_LABELS if digit in schedule_days]
    return ", ".join(labels) if labels else "—"


async def count_completions(db: AsyncSession, chore_id: int) -> int:
    result = await db.scalar(
        select(func.count())
        .select_from(ChoreCompletion)
        .where(ChoreCompletion.chore_id == chore_id)
    )
    return int(result or 0)


async def delete_chore(
    db: AsyncSession,
    chore: Chore,
    *,
    settings: Settings | None = None,
) -> int:
    """Hard-delete a chore and all of its completion history.

    Returns the number of completion rows removed.
    Prefer deactivate when you only want to stop the QR without losing history.
    """
    result = await db.execute(select(ChoreCompletion).where(ChoreCompletion.chore_id == chore.id))
    completions = list(result.scalars().all())
    removed = len(completions)

    if settings is not None:
        from contextlib import suppress

        from qr_chores.services.storage import StorageError, get_photo_storage

        storage = get_photo_storage(settings)
        for row in completions:
            if row.photo_object_key:
                with suppress(StorageError):
                    storage.delete(row.photo_object_key)

    await db.execute(delete(ChoreCompletion).where(ChoreCompletion.chore_id == chore.id))
    await db.delete(chore)
    await db.commit()
    return removed
