"""Timing classification unit tests."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from qr_chores.config import Settings
from qr_chores.models.chore import TimingStatus
from qr_chores.services.timeutil import (
    classify_timing,
    is_scheduled_on,
    timing_bonus_label,
    timing_rules_intro,
    timing_rules_lines,
    timing_status_label,
    timing_windows_for_due,
)


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


def test_classify_naive_completed_at_treated_as_app_tz() -> None:
    settings = _settings()
    day = date(2026, 7, 27)
    due = time(20, 0)
    # naive wall clock in America/Chicago
    completed = datetime(2026, 7, 27, 19, 50)
    assert completed.tzinfo is None
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


def test_timing_windows_for_due_example() -> None:
    settings = _settings()
    # Due 6:00 PM → early before 5:00 PM, late after 6:15 PM
    windows = timing_windows_for_due(time(18, 0), settings)
    assert windows.early_before == time(17, 0)
    assert windows.late_after == time(18, 15)
    assert windows.due_label == "6:00 PM"
    assert windows.early_before_label == "5:00 PM"
    assert windows.late_after_label == "6:15 PM"
    assert windows.early_window_minutes == 60
    assert windows.on_time_grace_minutes == 15


def test_timing_rules_lines_with_due_include_clock_times() -> None:
    settings = _settings()
    lines = timing_rules_lines(settings, due_time=time(18, 0))
    joined = " ".join(lines)
    assert "Early" in joined
    assert "5:00 PM" in joined
    assert "6:15 PM" in joined
    assert "6:00 PM" in joined
    assert "Late" in joined
    assert "On time" in joined
    assert timing_rules_intro(due_time=time(18, 0)).startswith("Timing for a")


def test_timing_rules_lines_general_use_minutes() -> None:
    settings = _settings()
    lines = timing_rules_lines(settings)
    joined = " ".join(lines)
    assert "60 minutes" in joined
    assert "15 minutes" in joined
    assert "Early" in joined
    assert timing_rules_intro().startswith("How timing works")


def test_timing_status_and_bonus_labels() -> None:
    assert timing_status_label(TimingStatus.early) == "Early"
    assert timing_status_label(TimingStatus.on_time) == "On time"
    assert timing_status_label(TimingStatus.late) == "Late"
    assert timing_bonus_label(TimingStatus.early) == "Early bonus"
    assert timing_bonus_label(TimingStatus.on_time) == "On-time bonus"
    assert timing_bonus_label(TimingStatus.late) == "Late bonus"
