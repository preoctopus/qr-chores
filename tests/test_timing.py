"""Timing classification unit tests."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from qr_chores.config import Settings
from qr_chores.models.chore import TimingStatus
from qr_chores.services.timeutil import classify_timing, is_scheduled_on


def _settings() -> Settings:
    return Settings(
        app_timezone="America/Chicago",
        on_time_grace_minutes=15,
        early_window_minutes=60,
    )


def test_is_scheduled_on_weekdays() -> None:
    # 2026-07-27 is a Monday
    monday = date(2026, 7, 27)
    assert is_scheduled_on("01234", monday)
    assert not is_scheduled_on("56", monday)
    assert is_scheduled_on("0123456", monday)


def test_classify_on_time() -> None:
    settings = _settings()
    tz = ZoneInfo("America/Chicago")
    day = date(2026, 7, 27)
    due = time(20, 0)
    completed = datetime(2026, 7, 27, 19, 50, tzinfo=tz)
    assert (
        classify_timing(completed_at=completed, due_time=due, local_date=day, settings=settings)
        == TimingStatus.on_time
    )


def test_classify_early() -> None:
    settings = _settings()
    tz = ZoneInfo("America/Chicago")
    day = date(2026, 7, 27)
    due = time(20, 0)
    completed = datetime(2026, 7, 27, 18, 0, tzinfo=tz)  # 2h before due
    assert (
        classify_timing(completed_at=completed, due_time=due, local_date=day, settings=settings)
        == TimingStatus.early
    )


def test_classify_late() -> None:
    settings = _settings()
    tz = ZoneInfo("America/Chicago")
    day = date(2026, 7, 27)
    due = time(20, 0)
    completed = datetime(2026, 7, 27, 20, 30, tzinfo=tz)  # past grace
    assert (
        classify_timing(completed_at=completed, due_time=due, local_date=day, settings=settings)
        == TimingStatus.late
    )


def test_classify_grace_still_on_time() -> None:
    settings = _settings()
    tz = ZoneInfo("America/Chicago")
    day = date(2026, 7, 27)
    due = time(20, 0)
    completed = datetime(2026, 7, 27, 20, 10, tzinfo=tz)  # within 15m grace
    assert (
        classify_timing(completed_at=completed, due_time=due, local_date=day, settings=settings)
        == TimingStatus.on_time
    )
