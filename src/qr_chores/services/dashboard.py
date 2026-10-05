"""Parent dashboard views: per-child Today board and day-grouped history."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from qr_chores.config import Settings
from qr_chores.models.chore import Chore, ChoreCompletion, TimingStatus
from qr_chores.models.user import User, UserRole
from qr_chores.services.chores import ChoreDayStatus, list_all_chores, today_board
from qr_chores.services.points import points_earned_today
from qr_chores.services.timeutil import app_tz, is_scheduled_on, local_today
from qr_chores.services.users import child_managed_by, list_children_for_parent

HISTORY_DEFAULT_DAYS = 14
HISTORY_MAX_DAYS = 92


class ChildNotManagedError(LookupError):
    """Requested child is not managed by this parent."""


@dataclass
class TodaySummary:
    total: int = 0
    done: int = 0
    pending: int = 0
    overdue: int = 0
    done_late: int = 0
    points_today: int = 0

    @property
    def percent(self) -> int:
        if self.total <= 0:
            return 0
        return int(100 * self.done / self.total)


@dataclass
class ChildDayGroup:
    child: User
    rows: list[ChoreDayStatus] = field(default_factory=list)
    points_today: int = 0

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def done(self) -> int:
        return sum(1 for r in self.rows if r.done)

    @property
    def overdue(self) -> int:
        return sum(1 for r in self.rows if r.is_late_pending)

    @property
    def percent(self) -> int:
        if not self.rows:
            return 0
        return int(100 * self.done / self.total)

    @property
    def name(self) -> str:
        return self.child.display_name or self.child.first_name


@dataclass
class TodayDashboard:
    local_date: date
    summary: TodaySummary
    groups: list[ChildDayGroup]
    board: list[ChoreDayStatus]


async def build_today_dashboard(
    db: AsyncSession,
    settings: Settings,
    parent_id: int,
    *,
    child_id: int | None = None,
) -> TodayDashboard:
    """Today's board for a parent, grouped by child, with summary counts.

    Raises :class:`ChildNotManagedError` when ``child_id`` is not one of the parent's children.
    """
    children = await list_children_for_parent(db, parent_id)
    if child_id is not None:
        children = [c for c in children if c.id == child_id]
        if not children:
            raise ChildNotManagedError(child_id)

    board = await today_board(db, settings, parent_id=parent_id)
    if child_id is not None:
        board = [r for r in board if r.chore.assignee_user_id == child_id]

    by_child: dict[int, list[ChoreDayStatus]] = {}
    for row in board:
        if row.chore.assignee_user_id is not None:
            by_child.setdefault(row.chore.assignee_user_id, []).append(row)

    groups: list[ChildDayGroup] = []
    for child in children:
        rows = by_child.get(child.id, [])
        if not child.is_active and not rows:
            continue
        groups.append(
            ChildDayGroup(
                child=child,
                rows=rows,
                points_today=await points_earned_today(db, child.id, settings),
            )
        )

    summary = TodaySummary(
        total=len(board),
        done=sum(1 for r in board if r.done),
        pending=sum(1 for r in board if not r.done and not r.is_late_pending),
        overdue=sum(1 for r in board if r.is_late_pending),
        done_late=sum(1 for r in board if r.done and r.timing == TimingStatus.late),
        points_today=sum(g.points_today for g in groups),
    )
    return TodayDashboard(
        local_date=local_today(settings),
        summary=summary,
        groups=groups,
        board=board,
    )


@dataclass
class HistoryDay:
    local_date: date
    completions: list[ChoreCompletion] = field(default_factory=list)
    missed: list[Chore] = field(default_factory=list)
    open_count: int = 0  # today only: scheduled, not done yet (not counted as missed)

    @property
    def done(self) -> int:
        return len(self.completions)

    @property
    def scheduled(self) -> int:
        return self.done + len(self.missed) + self.open_count

    @property
    def points(self) -> int:
        return sum(c.points_awarded for c in self.completions)

    @property
    def percent(self) -> int:
        if self.scheduled <= 0:
            return 0
        return int(100 * self.done / self.scheduled)

    @property
    def is_empty(self) -> bool:
        return self.scheduled == 0


@dataclass
class HistoryDaysResult:
    start_date: date
    end_date: date
    days: list[HistoryDay]  # newest first; every date in the window
    older_start: date | None = None
    older_end: date | None = None
    newer_start: date | None = None
    newer_end: date | None = None


def history_window(
    today: date,
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date]:
    """Clamp a requested window to ``HISTORY_MAX_DAYS`` ending no later than today."""
    end = min(end_date or today, today)
    start = start_date or end - timedelta(days=HISTORY_DEFAULT_DAYS - 1)
    if start > end:
        start = end
    if (end - start).days + 1 > HISTORY_MAX_DAYS:
        start = end - timedelta(days=HISTORY_MAX_DAYS - 1)
    return start, end


def _local_date_of(value: datetime, settings: Settings) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(app_tz(settings)).date()


async def get_history_days(
    db: AsyncSession,
    settings: Settings,
    parent_id: int,
    *,
    child_id: int | None = None,
    chore_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timing: TimingStatus | str | None = None,
) -> HistoryDaysResult:
    """Completions and missed chores per day for a parent's children.

    A chore is **missed** on a past day when it is active, was scheduled that
    weekday, already existed (``created_at``), and has no completion. Today's
    open chores are not missed. Missed rows are hidden when filtering by timing.
    """
    if isinstance(timing, str):
        try:
            timing = TimingStatus(timing)
        except ValueError:
            timing = None

    today = local_today(settings)
    start, end = history_window(today, start_date, end_date)
    span = (end - start).days + 1

    child_ids = select(User.id).where(User.role == UserRole.child, child_managed_by(parent_id))
    where = [
        ChoreCompletion.user_id.in_(child_ids),
        ChoreCompletion.local_date >= start,
        ChoreCompletion.local_date <= end,
    ]
    if child_id is not None:
        where.append(ChoreCompletion.user_id == child_id)
    if chore_id is not None:
        where.append(ChoreCompletion.chore_id == chore_id)
    if timing is not None:
        where.append(ChoreCompletion.timing == timing)

    result = await db.execute(
        select(ChoreCompletion)
        .options(selectinload(ChoreCompletion.chore), selectinload(ChoreCompletion.user))
        .where(*where)
        .order_by(ChoreCompletion.completed_at.desc())
    )
    completions = list(result.scalars().all())

    days = {
        start + timedelta(days=i): HistoryDay(local_date=start + timedelta(days=i))
        for i in range(span)
    }
    done_keys: set[tuple[int, date]] = set()
    for c in completions:
        days[c.local_date].completions.append(c)
        done_keys.add((c.chore_id, c.local_date))

    chores: list[Chore] = []
    if timing is None:
        chores = await list_all_chores(db, include_inactive=False, parent_id=parent_id)
        if child_id is not None:
            chores = [c for c in chores if c.assignee_user_id == child_id]
        if chore_id is not None:
            chores = [c for c in chores if c.id == chore_id]
        for chore in chores:
            created = _local_date_of(chore.created_at, settings)
            for day, bucket in days.items():
                if day < created or not is_scheduled_on(chore.schedule_days, day):
                    continue
                if (chore.id, day) in done_keys:
                    continue
                if day < today:
                    bucket.missed.append(chore)
                else:
                    bucket.open_count += 1
        for bucket in days.values():
            bucket.missed.sort(key=lambda ch: (ch.due_time, ch.title))

    # Navigation: stop "older" at the earliest data in scope.
    earliest_q = select(func.min(ChoreCompletion.local_date)).where(
        ChoreCompletion.user_id.in_(child_ids)
    )
    earliest_completion = await db.scalar(earliest_q)
    candidates = [earliest_completion] if earliest_completion else []
    candidates += [_local_date_of(c.created_at, settings) for c in chores]
    earliest = min(candidates) if candidates else start

    res = HistoryDaysResult(
        start_date=start,
        end_date=end,
        days=sorted(days.values(), key=lambda d: d.local_date, reverse=True),
    )
    if earliest < start:
        res.older_end = start - timedelta(days=1)
        res.older_start = res.older_end - timedelta(days=span - 1)
    if end < today:
        res.newer_start = end + timedelta(days=1)
        res.newer_end = min(end + timedelta(days=span), today)
    return res
