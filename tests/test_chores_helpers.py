"""Unit tests for chore parsing and labeling helpers."""

from datetime import time

import pytest

from qr_chores.models.chore import TimingStatus
from qr_chores.services.chores import (
    ChoreDayStatus,
    parse_due_time,
    parse_schedule_days,
    schedule_labels,
)
from qr_chores.services.timeutil import format_due_time


def test_parse_due_time_hhmm() -> None:
    assert parse_due_time("09:30") == time(9, 30)


def test_parse_due_time_with_seconds() -> None:
    assert parse_due_time("20:00:15") == time(20, 0, 15)


def test_parse_due_time_invalid() -> None:
    with pytest.raises(ValueError):
        parse_due_time("nope")


def test_parse_schedule_days_defaults() -> None:
    assert parse_schedule_days(None) == "0123456"
    assert parse_schedule_days([]) == "0123456"
    assert parse_schedule_days(["x", "y"]) == "0123456"


def test_parse_schedule_days_weekdays() -> None:
    assert parse_schedule_days(["4", "0", "1", "2", "3"]) == "01234"


def test_schedule_labels() -> None:
    assert schedule_labels("0123456") == "Every day"
    assert schedule_labels("01234") == "Weekdays"
    assert schedule_labels("56") == "Weekends"
    assert schedule_labels("05") == "Mon, Sat"
    assert schedule_labels("") == "—"


def test_format_due_time() -> None:
    assert format_due_time(time(0, 5)) == "12:05 AM"
    assert format_due_time(time(12, 0)) == "12:00 PM"
    assert format_due_time(time(15, 45)) == "3:45 PM"


def test_chore_day_status_labels() -> None:
    class FakeChore:
        pass

    pending = ChoreDayStatus(
        chore=FakeChore(),  # type: ignore[arg-type]
        done=False,
        completion=None,
        timing=None,
        is_late_pending=False,
    )
    assert pending.status_label == "Pending"
    assert pending.status_kind == "pending"

    late = ChoreDayStatus(
        chore=FakeChore(),  # type: ignore[arg-type]
        done=False,
        completion=None,
        timing=None,
        is_late_pending=True,
    )
    assert late.status_label == "Late"
    assert late.status_kind == "late"

    done = ChoreDayStatus(
        chore=FakeChore(),  # type: ignore[arg-type]
        done=True,
        completion=None,
        timing=TimingStatus.on_time,
        is_late_pending=False,
    )
    assert done.status_label == "Done"
    assert done.status_kind == "done"

    early = ChoreDayStatus(
        chore=FakeChore(),  # type: ignore[arg-type]
        done=True,
        completion=None,
        timing=TimingStatus.early,
        is_late_pending=False,
    )
    assert "early" in early.status_label.lower()

    late_done = ChoreDayStatus(
        chore=FakeChore(),  # type: ignore[arg-type]
        done=True,
        completion=None,
        timing=TimingStatus.late,
        is_late_pending=False,
    )
    assert "late" in late_done.status_label.lower()
