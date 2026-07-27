"""Unit tests for /api/v1 Pydantic request/response schemas."""

from datetime import UTC, date, datetime, time

import pytest
from pydantic import ValidationError

from qr_chores.schemas.auth import LoginRequest, TokenResponse, UserOut
from qr_chores.schemas.chores import (
    AchievementProgressOut,
    AchievementsResponse,
    BoardItemOut,
    ChoreConfirmOut,
    ChoreSummaryOut,
    CompleteResponse,
    CompletionSummaryOut,
    HomeResponse,
    PointsBreakdownOut,
    UnlockOut,
)
from qr_chores.schemas.parent import (
    ChoreCreate,
    ChoreDeleteResponse,
    ChoreListResponse,
    ChoreUpdate,
    HistoryItemOut,
    HistoryResponse,
    QrInfoOut,
    TodayResponse,
)
from qr_chores.schemas.rewards import (
    AchievementAdminOut,
    AchievementCreate,
    AchievementUpdate,
    RewardsResponse,
    TimingBonusesOut,
    TimingBonusesUpdate,
)

# --- Auth ---


def test_login_request_ok() -> None:
    body = LoginRequest(email="a@b.com", password="secret")
    assert body.email == "a@b.com"
    assert body.password == "secret"


def test_login_request_empty_rejected() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email="", password="x")
    with pytest.raises(ValidationError):
        LoginRequest(email="a@b.com", password="")


def test_user_out_and_token_response() -> None:
    user = UserOut(
        id=1,
        email="dad@example.com",
        first_name="Dad",
        last_name="Example",
        display_name="Dad Example",
        role="parent",
        points_balance=0,
    )
    token = TokenResponse(access_token="abc", expires_in=1200, user=user)
    assert token.token_type == "bearer"
    assert token.user.role == "parent"


# --- Chore write schemas ---


def test_chore_create_defaults_and_strip() -> None:
    body = ChoreCreate(title="  Trash  ", due_time=time(19, 30), assignee_user_id=1)
    assert body.title == "Trash"
    assert body.schedule_days == "0123456"
    assert body.photo_policy == "none"
    assert body.base_points == 10
    assert body.description is None
    assert body.assignee_user_id == 1


def test_chore_create_description_blank_to_none() -> None:
    body = ChoreCreate(title="X", due_time=time(10, 0), description="   ", assignee_user_id=1)
    assert body.description is None
    body_none = ChoreCreate(title="X", due_time=time(10, 0), description=None, assignee_user_id=1)
    assert body_none.description is None


def test_chore_create_schedule_days_normalized() -> None:
    body = ChoreCreate(title="X", due_time=time(10, 0), schedule_days="4201x9", assignee_user_id=1)
    assert body.schedule_days == "0124"


def test_chore_create_schedule_days_empty_defaults() -> None:
    body = ChoreCreate(title="X", due_time=time(10, 0), schedule_days="zzzz", assignee_user_id=1)
    assert body.schedule_days == "0123456"


def test_chore_create_photo_policy_valid() -> None:
    for policy in ("required", "optional", "none"):
        body = ChoreCreate(title="X", due_time=time(10, 0), photo_policy=policy, assignee_user_id=1)
        assert body.photo_policy == policy


def test_chore_create_photo_policy_invalid() -> None:
    with pytest.raises(ValidationError) as exc:
        ChoreCreate(title="X", due_time=time(10, 0), photo_policy="maybe", assignee_user_id=1)
    assert "photo_policy" in str(exc.value)


def test_chore_create_blank_title_rejected() -> None:
    with pytest.raises(ValidationError):
        ChoreCreate(title="   ", due_time=time(10, 0), assignee_user_id=1)


def test_chore_create_negative_points_rejected() -> None:
    with pytest.raises(ValidationError):
        ChoreCreate(title="X", due_time=time(10, 0), base_points=-1, assignee_user_id=1)


def test_chore_update_partial_and_none_fields() -> None:
    body = ChoreUpdate()
    assert body.title is None
    assert body.clear_description is False

    body = ChoreUpdate(title="  New  ", schedule_days="65", photo_policy="required")
    assert body.title == "New"
    assert body.schedule_days == "56"
    assert body.photo_policy == "required"


def test_chore_update_blank_title_rejected() -> None:
    with pytest.raises(ValidationError):
        ChoreUpdate(title="  ")


def test_chore_update_title_none_passthrough() -> None:
    body = ChoreUpdate(title=None, photo_policy=None)
    assert body.title is None
    assert body.photo_policy is None


def test_chore_update_invalid_photo_policy() -> None:
    with pytest.raises(ValidationError):
        ChoreUpdate(photo_policy="nope")


def test_chore_update_schedule_days_none_passthrough() -> None:
    body = ChoreUpdate(schedule_days=None)
    assert body.schedule_days is None


def test_chore_update_schedule_garbage_defaults() -> None:
    body = ChoreUpdate(schedule_days="xyz")
    assert body.schedule_days == "0123456"


# --- Rewards schemas ---


def test_timing_bonuses_update_ok() -> None:
    body = TimingBonusesUpdate(
        early_bonus_points=5,
        on_time_bonus_points=2,
        late_bonus_points=0,
    )
    assert body.early_bonus_points == 5


def test_timing_bonuses_early_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        TimingBonusesUpdate(
            early_bonus_points=-1,
            on_time_bonus_points=0,
            late_bonus_points=0,
        )


def test_timing_bonuses_late_negative_allowed() -> None:
    body = TimingBonusesUpdate(
        early_bonus_points=0,
        on_time_bonus_points=0,
        late_bonus_points=-2,
    )
    assert body.late_bonus_points == -2


def test_achievement_create_ok_and_stripping() -> None:
    body = AchievementCreate(
        title="  Early bird  ",
        description="  go  ",
        icon_key="  bird  ",
        criteria_type="complete_early_count",
        threshold=5,
        points_reward=20,
    )
    assert body.title == "Early bird"
    assert body.description == "go"
    assert body.icon_key == "bird"
    assert body.criteria_type == "complete_early_count"


def test_achievement_create_icon_defaults() -> None:
    body = AchievementCreate(title="A", criteria_type="streak_days", icon_key="")
    assert body.icon_key == "star"
    body2 = AchievementCreate(title="A", criteria_type="streak_days", icon_key="   ")
    assert body2.icon_key == "star"


def test_achievement_create_invalid_criteria() -> None:
    with pytest.raises(ValidationError) as exc:
        AchievementCreate(title="A", criteria_type="not_a_thing")
    assert "criteria_type" in str(exc.value)


def test_achievement_create_blank_title() -> None:
    with pytest.raises(ValidationError):
        AchievementCreate(title="  ", criteria_type="total_completions")


def test_achievement_create_threshold_minimum() -> None:
    with pytest.raises(ValidationError):
        AchievementCreate(title="A", criteria_type="total_completions", threshold=0)


def test_achievement_create_all_criteria_types() -> None:
    for ct in (
        "total_completions",
        "complete_on_time_count",
        "complete_early_count",
        "photo_completions",
        "streak_days",
    ):
        body = AchievementCreate(title="A", criteria_type=ct)
        assert body.criteria_type == ct


def test_achievement_update_partial() -> None:
    body = AchievementUpdate()
    assert body.title is None
    assert body.criteria_type is None

    body = AchievementUpdate(title="  B  ", criteria_type="photo_completions", threshold=3)
    assert body.title == "B"
    assert body.criteria_type == "photo_completions"
    assert body.threshold == 3


def test_achievement_update_blank_title_rejected() -> None:
    with pytest.raises(ValidationError):
        AchievementUpdate(title=" ")


def test_achievement_update_invalid_criteria() -> None:
    with pytest.raises(ValidationError):
        AchievementUpdate(criteria_type="bad")


def test_achievement_update_criteria_none_passthrough() -> None:
    body = AchievementUpdate(criteria_type=None)
    assert body.criteria_type is None


# --- Response models constructible ---


def _chore_summary() -> ChoreSummaryOut:
    return ChoreSummaryOut(
        id=1,
        title="Chore",
        qr_token="t",
        due_time=time(20, 0),
        schedule_days="0123456",
        photo_policy="none",
        base_points=10,
        is_active=True,
    )


def _completion_summary() -> CompletionSummaryOut:
    return CompletionSummaryOut(
        id=1,
        local_date=date(2026, 7, 26),
        completed_at=datetime(2026, 7, 26, 19, 0, tzinfo=UTC),
        timing="on_time",
        points_awarded=10,
        has_photo=False,
    )


def test_response_models_roundtrip_shapes() -> None:
    chore = _chore_summary()
    completion = _completion_summary()
    board = BoardItemOut(
        chore=chore,
        done=True,
        status_label="Done",
        status_kind="done",
        is_late_pending=False,
        timing="on_time",
        completion=completion,
    )
    unlock = UnlockOut(
        id=1,
        title="U",
        icon_key="star",
        points_reward=5,
        unlocked_at=None,
    )
    home = HomeResponse(
        local_date=date(2026, 7, 26),
        points_balance=10,
        points_today=10,
        done_count=1,
        total_count=1,
        board=[board],
        recent_unlocks=[unlock],
    )
    assert home.total_count == 1

    confirm = ChoreConfirmOut(
        chore=chore,
        scheduled_today=True,
        already_done=False,
        is_late_pending=False,
        completion=None,
    )
    assert confirm.already_done is False

    complete = CompleteResponse(
        already_done=False,
        chore=chore,
        completion=completion,
        points=PointsBreakdownOut(base=10, timing_bonus=2, achievement_points=0, total=12),
        unlocks=[],
    )
    assert complete.points.total == 12

    achievements = AchievementsResponse(
        points_balance=10,
        unlocked_count=0,
        achievements=[
            AchievementProgressOut(
                id=1,
                title="A",
                icon_key="star",
                criteria_type="total_completions",
                points_reward=5,
                unlocked=False,
                progress=0,
                threshold=5,
                percent=0,
            )
        ],
    )
    assert achievements.unlocked_count == 0

    today = TodayResponse(local_date=date(2026, 7, 26), board=[board])
    assert len(today.board) == 1

    history = HistoryResponse(
        items=[
            HistoryItemOut(
                completion=completion,
                chore_id=1,
                chore_title="Chore",
                user_id=2,
            )
        ],
        limit=50,
    )
    assert history.limit == 50

    chores = ChoreListResponse(chores=[chore])
    assert len(chores.chores) == 1

    qr = QrInfoOut(
        chore_id=1,
        title="Chore",
        qr_token="t",
        qr_url="http://test/c/t",
        png_path="/api/v1/chores/1/qr.png",
    )
    assert qr.png_path.endswith(".png")

    deleted = ChoreDeleteResponse(deleted=True, chore_id=1, completions_removed=2)
    assert deleted.completions_removed == 2

    rewards = RewardsResponse(
        bonuses=TimingBonusesOut(
            early_bonus_points=5,
            on_time_bonus_points=2,
            late_bonus_points=0,
        ),
        achievements=[
            AchievementAdminOut(
                id=1,
                title="A",
                description="",
                icon_key="star",
                criteria_type="streak_days",
                threshold=3,
                points_reward=10,
                is_active=True,
            )
        ],
    )
    assert rewards.bonuses.early_bonus_points == 5
