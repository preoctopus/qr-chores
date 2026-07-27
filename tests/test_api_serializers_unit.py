"""Unit tests for /api/v1 response serializers."""

from datetime import UTC, date, datetime, time, timedelta

from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy, TimingStatus
from qr_chores.models.rewards import Achievement, CriteriaType, UserAchievement
from qr_chores.routers.api.serializers import (
    board_item,
    chore_summary,
    completion_summary,
    is_late_pending_for_chore,
    unlock_from_achievement,
    unlock_from_user_achievement,
)
from qr_chores.services.chores import ChoreDayStatus


def _chore(**kwargs) -> Chore:
    defaults = {
        "id": 7,
        "title": "Dishes",
        "description": "Rinse first",
        "qr_token": "tok-abc",
        "due_time": time(20, 0),
        "schedule_days": "0123456",
        "photo_policy": PhotoPolicy.optional,
        "base_points": 15,
        "is_active": True,
    }
    defaults.update(kwargs)
    return Chore(**defaults)


def _completion(**kwargs) -> ChoreCompletion:
    defaults = {
        "id": 3,
        "chore_id": 7,
        "user_id": 2,
        "local_date": date(2026, 7, 26),
        "completed_at": datetime(2026, 7, 26, 19, 30, tzinfo=UTC),
        "timing": TimingStatus.on_time,
        "photo_object_key": "completions/7/2026-07-26/x.png",
        "points_awarded": 17,
    }
    defaults.update(kwargs)
    return ChoreCompletion(**defaults)


def test_chore_summary() -> None:
    out = chore_summary(_chore())
    assert out.id == 7
    assert out.title == "Dishes"
    assert out.description == "Rinse first"
    assert out.qr_token == "tok-abc"
    assert out.due_time == time(20, 0)
    assert out.schedule_days == "0123456"
    assert out.photo_policy == "optional"
    assert out.base_points == 15
    assert out.is_active is True


def test_chore_summary_none_description() -> None:
    out = chore_summary(_chore(description=None, photo_policy=PhotoPolicy.none, is_active=False))
    assert out.description is None
    assert out.photo_policy == "none"
    assert out.is_active is False


def test_completion_summary_with_photo() -> None:
    out = completion_summary(_completion())
    assert out.id == 3
    assert out.local_date == date(2026, 7, 26)
    assert out.timing == "on_time"
    assert out.points_awarded == 17
    assert out.has_photo is True


def test_completion_summary_without_photo() -> None:
    out = completion_summary(_completion(photo_object_key=None, timing=TimingStatus.late))
    assert out.has_photo is False
    assert out.timing == "late"


def test_board_item_pending() -> None:
    chore = _chore()
    row = ChoreDayStatus(
        chore=chore,
        done=False,
        completion=None,
        timing=None,
        is_late_pending=False,
    )
    out = board_item(row)
    assert out.chore.id == chore.id
    assert out.done is False
    assert out.status_label == "Pending"
    assert out.status_kind == "pending"
    assert out.is_late_pending is False
    assert out.timing is None
    assert out.completion is None


def test_board_item_done_with_completion() -> None:
    chore = _chore()
    completion = _completion(timing=TimingStatus.early)
    row = ChoreDayStatus(
        chore=chore,
        done=True,
        completion=completion,
        timing=TimingStatus.early,
        is_late_pending=False,
    )
    out = board_item(row)
    assert out.done is True
    assert out.status_kind == "done"
    assert out.timing == "early"
    assert out.completion is not None
    assert out.completion.id == completion.id


def test_board_item_late_pending() -> None:
    row = ChoreDayStatus(
        chore=_chore(),
        done=False,
        completion=None,
        timing=None,
        is_late_pending=True,
    )
    out = board_item(row)
    assert out.status_label == "Late"
    assert out.status_kind == "late"
    assert out.is_late_pending is True


def test_unlock_from_achievement() -> None:
    ach = Achievement(
        id=9,
        title="Streak",
        description="3 days",
        icon_key="fire",
        criteria_type=CriteriaType.streak_days,
        criteria_json='{"days": 3}',
        points_reward=25,
        is_active=True,
    )
    unlocked_at = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    out = unlock_from_achievement(ach, unlocked_at=unlocked_at)
    assert out.id == 9
    assert out.title == "Streak"
    assert out.icon_key == "fire"
    assert out.points_reward == 25
    assert out.unlocked_at == unlocked_at


def test_unlock_from_achievement_default_unlocked_at() -> None:
    ach = Achievement(
        id=1,
        title="First",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.total_completions,
        criteria_json='{"count": 1}',
        points_reward=5,
        is_active=True,
    )
    out = unlock_from_achievement(ach)
    assert out.unlocked_at is None


def test_unlock_from_user_achievement() -> None:
    ach = Achievement(
        id=4,
        title="Photo pro",
        description="snap",
        icon_key="camera",
        criteria_type=CriteriaType.photo_completions,
        criteria_json='{"count": 5}',
        points_reward=10,
        is_active=True,
    )
    unlocked_at = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
    ua = UserAchievement(
        id=1,
        user_id=2,
        achievement_id=4,
        unlocked_at=unlocked_at,
    )
    # Relationship not loaded from DB — attach directly for unit test.
    ua.achievement = ach  # type: ignore[assignment]
    out = unlock_from_user_achievement(ua)
    assert out.id == 4
    assert out.title == "Photo pro"
    assert out.unlocked_at == unlocked_at


def test_is_late_pending_not_scheduled() -> None:
    chore = _chore(due_time=time(8, 0))
    now = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
    assert (
        is_late_pending_for_chore(
            chore=chore,
            completion=None,
            scheduled=False,
            now=now,
            today=date(2026, 7, 26),
            grace_minutes=15,
        )
        is False
    )


def test_is_late_pending_already_done() -> None:
    chore = _chore(due_time=time(8, 0))
    now = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
    assert (
        is_late_pending_for_chore(
            chore=chore,
            completion=_completion(),
            scheduled=True,
            now=now,
            today=date(2026, 7, 26),
            grace_minutes=15,
        )
        is False
    )


def test_is_late_pending_before_due() -> None:
    chore = _chore(due_time=time(20, 0))
    now = datetime(2026, 7, 26, 19, 0, tzinfo=UTC)
    assert (
        is_late_pending_for_chore(
            chore=chore,
            completion=None,
            scheduled=True,
            now=now,
            today=date(2026, 7, 26),
            grace_minutes=15,
        )
        is False
    )


def test_is_late_pending_within_grace() -> None:
    chore = _chore(due_time=time(20, 0))
    now = datetime(2026, 7, 26, 20, 10, tzinfo=UTC)
    assert (
        is_late_pending_for_chore(
            chore=chore,
            completion=None,
            scheduled=True,
            now=now,
            today=date(2026, 7, 26),
            grace_minutes=15,
        )
        is False
    )


def test_is_late_pending_after_grace() -> None:
    chore = _chore(due_time=time(20, 0))
    today = date(2026, 7, 26)
    due = datetime.combine(today, time(20, 0), tzinfo=UTC)
    now = due + timedelta(minutes=16)
    assert (
        is_late_pending_for_chore(
            chore=chore,
            completion=None,
            scheduled=True,
            now=now,
            today=today,
            grace_minutes=15,
        )
        is True
    )
