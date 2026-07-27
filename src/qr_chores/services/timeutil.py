"""Timezone and schedule helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from qr_chores.config import Settings
from qr_chores.models.chore import TimingStatus

# Short labels for UI chips and celebration copy
TIMING_STATUS_LABELS: dict[TimingStatus, str] = {
    TimingStatus.early: "Early",
    TimingStatus.on_time: "On time",
    TimingStatus.late: "Late",
}

# Points breakdown labels (celebration)
TIMING_BONUS_LABELS: dict[TimingStatus, str] = {
    TimingStatus.early: "Early bonus",
    TimingStatus.on_time: "On-time bonus",
    TimingStatus.late: "Late bonus",
}

# Optional pinned instant for tests (timezone-aware). Production leaves this None.
_frozen_instant: datetime | None = None


def app_tz(settings: Settings) -> ZoneInfo:
    return ZoneInfo(settings.app_timezone)


def local_now(settings: Settings) -> datetime:
    """Current wall-clock time in APP_TIMEZONE (or a test freeze)."""
    tz = app_tz(settings)
    if _frozen_instant is not None:
        return _frozen_instant.astimezone(tz)
    return datetime.now(tz=tz)


def local_today(settings: Settings) -> date:
    return local_now(settings).date()


def _resolve_freeze_instant(
    when: datetime | date,
    *,
    tz: str | ZoneInfo,
) -> datetime:
    zone = ZoneInfo(tz) if isinstance(tz, str) else tz
    if isinstance(when, datetime):
        if when.tzinfo is None:
            return when.replace(tzinfo=zone)
        return when
    # date only — noon local avoids DST midnight edge cases
    return datetime.combine(when, time(12, 0), tzinfo=zone)


@contextmanager
def frozen_at(
    when: datetime | date,
    *,
    tz: str | ZoneInfo = "America/Chicago",
) -> Iterator[datetime]:
    """Pin :func:`local_now` / :func:`local_today` for the duration of the block.

    Intended for tests (schedule days, timing windows, day boundaries). Nestable.

    * ``date`` → that local calendar day at 12:00.
    * naive ``datetime`` → interpreted as wall clock in ``tz``.
    * aware ``datetime`` → converted when read via ``local_now``.
    """
    global _frozen_instant
    instant = _resolve_freeze_instant(when, tz=tz)
    previous = _frozen_instant
    _frozen_instant = instant
    try:
        yield instant
    finally:
        _frozen_instant = previous


def clear_frozen_time() -> None:
    """Drop any pinned clock (tests / fixtures)."""
    global _frozen_instant
    _frozen_instant = None


def is_scheduled_on(schedule_days: str, day: date) -> bool:
    """Return True if chore runs on this calendar day (weekday digit in schedule_days)."""
    return str(day.weekday()) in (schedule_days or "")


def classify_timing(
    *,
    completed_at: datetime,
    due_time: time,
    local_date: date,
    settings: Settings,
) -> TimingStatus:
    """Classify completion relative to due time on local_date."""
    tz = app_tz(settings)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=tz)
    else:
        completed_at = completed_at.astimezone(tz)

    due_dt = datetime.combine(local_date, due_time, tzinfo=tz)
    grace = timedelta(minutes=settings.on_time_grace_minutes)
    early_window = timedelta(minutes=settings.early_window_minutes)

    if completed_at > due_dt + grace:
        return TimingStatus.late
    if completed_at < due_dt - early_window:
        return TimingStatus.early
    return TimingStatus.on_time


def format_due_time(due: time) -> str:
    # %-I is POSIX-only; use %#I on Windows — we target macOS/Linux/Cloud Run
    hour = due.hour % 12 or 12
    ampm = "AM" if due.hour < 12 else "PM"
    return f"{hour}:{due.minute:02d} {ampm}"


def _shift_time(due: time, *, minutes: int) -> time:
    """Shift a wall-clock time by minutes (can cross midnight; returns time only)."""
    base = datetime.combine(date(2000, 1, 1), due)
    return (base + timedelta(minutes=minutes)).time()


@dataclass(frozen=True, slots=True)
class TimingWindows:
    """Concrete cutoffs for a chore due time, for plain-language UI."""

    due_time: time
    early_before: time  # complete strictly before this → early
    late_after: time  # complete strictly after this → late
    early_window_minutes: int
    on_time_grace_minutes: int

    @property
    def due_label(self) -> str:
        return format_due_time(self.due_time)

    @property
    def early_before_label(self) -> str:
        return format_due_time(self.early_before)

    @property
    def late_after_label(self) -> str:
        return format_due_time(self.late_after)


def timing_windows_for_due(due_time: time, settings: Settings) -> TimingWindows:
    """Return Early / On time / Late cutoffs for a due time."""
    early_mins = max(0, int(settings.early_window_minutes))
    grace_mins = max(0, int(settings.on_time_grace_minutes))
    return TimingWindows(
        due_time=due_time,
        early_before=_shift_time(due_time, minutes=-early_mins),
        late_after=_shift_time(due_time, minutes=grace_mins),
        early_window_minutes=early_mins,
        on_time_grace_minutes=grace_mins,
    )


def timing_status_label(timing: TimingStatus) -> str:
    return TIMING_STATUS_LABELS.get(timing, timing.value.replace("_", " ").title())


def timing_bonus_label(timing: TimingStatus) -> str:
    return TIMING_BONUS_LABELS.get(timing, "Timing bonus")


def timing_rules_lines(settings: Settings, *, due_time: time | None = None) -> list[str]:
    """Plain-language rules for Early / On time / Late.

    When ``due_time`` is set, lines include concrete clock times for that chore.
    Otherwise they describe the windows in minutes (parent Rewards page).
    """
    early_mins = max(0, int(settings.early_window_minutes))
    grace_mins = max(0, int(settings.on_time_grace_minutes))

    if due_time is not None:
        w = timing_windows_for_due(due_time, settings)
        return [
            f"Early — finish before {w.early_before_label} "
            f"(more than {early_mins} min before due).",
            f"On time — from {w.early_before_label} through {w.late_after_label} "
            f"(due {w.due_label}, plus {grace_mins} min grace).",
            f"Late — after {w.late_after_label}. You can still finish the same day.",
        ]

    return [
        f"Early — more than {early_mins} minutes before the chore’s due time.",
        f"On time — from {early_mins} minutes before due through due time "
        f"plus {grace_mins} minutes of grace.",
        "Late — after the grace window. Completing the same day is still allowed.",
    ]


def timing_rules_intro(*, due_time: time | None = None) -> str:
    """One-line intro above the rules list."""
    if due_time is not None:
        return f"Timing for a {format_due_time(due_time)} due time:"
    return "How timing works for every chore:"
