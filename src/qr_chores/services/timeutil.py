"""Timezone and schedule helpers."""

from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo

from qr_chores.config import Settings
from qr_chores.models.chore import TimingStatus


def app_tz(settings: Settings) -> ZoneInfo:
    return ZoneInfo(settings.app_timezone)


def local_now(settings: Settings) -> datetime:
    return datetime.now(tz=app_tz(settings))


def local_today(settings: Settings) -> date:
    return local_now(settings).date()


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
