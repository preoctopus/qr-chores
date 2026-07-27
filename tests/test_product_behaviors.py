"""Product-rule acceptance tests for expected family-app behaviors.

Covers domain contracts that matter to parents/children without re-testing
HTTP plumbing already covered in route-focused modules:

- Points land in PointLedger (base + timing bonus) on completion
- Achievements unlock once when criteria met, with ledger rewards
- Photo policies: required / optional / none
- Double-complete same day awards no extra points
- Timing bonuses for early / on_time / late
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from qr_chores.auth.passwords import hash_password
from qr_chores.config import Settings
from qr_chores.db import Base
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy, TimingStatus
from qr_chores.models.rewards import Achievement, CriteriaType, PointLedger, UserAchievement
from qr_chores.models.user import User, UserRole
from qr_chores.services.achievements import evaluate_achievements
from qr_chores.services.completion import (
    CompletionError,
    PhotoUpload,
    complete_chore,
)
from qr_chores.services.points import points_balance, set_setting
from qr_chores.services.qr import new_qr_token
from qr_chores.services.timeutil import local_today

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
async def domain(tmp_path):
    """Isolated session + child user + settings for domain product rules."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    settings = Settings(
        app_timezone="America/Chicago",
        photo_storage="local",
        photo_local_dir=str(tmp_path / "uploads"),
        on_time_grace_minutes=15,
        early_window_minutes=60,
    )
    async with factory() as session:
        child = User(
            email="child@example.com",
            display_name="Child",
            password_hash=hash_password("x"),
            role=UserRole.child,
            is_active=True,
        )
        session.add(child)
        await session.commit()
        await session.refresh(child)
        yield session, child, settings
    await engine.dispose()


async def _chore(session: AsyncSession, **kwargs) -> Chore:
    defaults = {
        "title": "Product chore",
        "qr_token": new_qr_token(),
        "due_time": time(23, 59),
        "schedule_days": "0123456",
        "photo_policy": PhotoPolicy.none,
        "base_points": 10,
        "is_active": True,
    }
    defaults.update(kwargs)
    chore = Chore(**defaults)
    session.add(chore)
    await session.commit()
    await session.refresh(chore)
    return chore


async def _achievement(
    session: AsyncSession,
    *,
    title: str,
    criteria_type: CriteriaType,
    threshold: int = 1,
    points_reward: int = 10,
    is_active: bool = True,
) -> Achievement:
    key = "days" if criteria_type == CriteriaType.streak_days else "count"
    ach = Achievement(
        title=title,
        description=title,
        icon_key="star",
        criteria_type=criteria_type,
        criteria_json=f'{{"{key}": {threshold}}}',
        points_reward=points_reward,
        is_active=is_active,
    )
    session.add(ach)
    await session.commit()
    await session.refresh(ach)
    return ach


# ---------------------------------------------------------------------------
# Points on successful completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completion_adds_base_points_to_ledger(domain) -> None:
    session, child, settings = domain
    await set_setting(session, "early_bonus_points", "0")
    await set_setting(session, "on_time_bonus_points", "0")
    await set_setting(session, "late_bonus_points", "0")
    await session.commit()

    chore = await _chore(session, base_points=15)
    result = await complete_chore(session, chore=chore, user=child, settings=settings)

    assert result.already_done is False
    assert result.points.base == 15
    assert result.points.timing_bonus == 0
    assert result.completion.points_awarded == 15
    assert await points_balance(session, child.id) == 15

    ledger = (
        (
            await session.execute(
                select(PointLedger).where(
                    PointLedger.user_id == child.id,
                    PointLedger.ref_type == "completion",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(ledger) == 1
    assert ledger[0].delta == 15
    assert "Product chore" in ledger[0].reason or "Completed" in ledger[0].reason


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("timing", "bonus_key", "bonus_value"),
    [
        (TimingStatus.early, "early_bonus_points", 7),
        (TimingStatus.on_time, "on_time_bonus_points", 4),
        (TimingStatus.late, "late_bonus_points", 1),
        (TimingStatus.late, "late_bonus_points", -2),
    ],
)
async def test_timing_bonus_awarded_per_status(
    domain, timing: TimingStatus, bonus_key: str, bonus_value: int
) -> None:
    session, child, settings = domain
    for key in ("early_bonus_points", "on_time_bonus_points", "late_bonus_points"):
        await set_setting(session, key, "0")
    await set_setting(session, bonus_key, str(bonus_value))
    await session.commit()

    chore = await _chore(session, base_points=10)
    with patch(
        "qr_chores.services.completion.classify_timing",
        return_value=timing,
    ):
        result = await complete_chore(session, chore=chore, user=child, settings=settings)

    assert result.completion.timing == timing
    assert result.points.base == 10
    assert result.points.timing_bonus == bonus_value
    assert result.completion.points_awarded == 10 + bonus_value
    assert await points_balance(session, child.id) == 10 + bonus_value

    bonus_rows = (
        (
            await session.execute(
                select(PointLedger).where(
                    PointLedger.user_id == child.id,
                    PointLedger.ref_type == "completion_bonus",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(bonus_rows) == 1
    assert bonus_rows[0].delta == bonus_value
    assert "Timing" in bonus_rows[0].reason


@pytest.mark.asyncio
async def test_zero_timing_bonus_writes_no_bonus_ledger_row(domain) -> None:
    session, child, settings = domain
    await set_setting(session, "early_bonus_points", "0")
    await set_setting(session, "on_time_bonus_points", "0")
    await set_setting(session, "late_bonus_points", "0")
    await session.commit()

    chore = await _chore(session, base_points=8)
    with patch(
        "qr_chores.services.completion.classify_timing",
        return_value=TimingStatus.late,
    ):
        result = await complete_chore(session, chore=chore, user=child, settings=settings)

    assert result.points.timing_bonus == 0
    assert await points_balance(session, child.id) == 8
    bonus_count = await session.scalar(
        select(func.count())
        .select_from(PointLedger)
        .where(PointLedger.ref_type == "completion_bonus")
    )
    assert bonus_count == 0


# ---------------------------------------------------------------------------
# Double-complete same day
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_double_complete_does_not_reaward_points_or_achievements(domain) -> None:
    session, child, settings = domain
    await set_setting(session, "early_bonus_points", "0")
    await set_setting(session, "on_time_bonus_points", "0")
    await set_setting(session, "late_bonus_points", "0")
    await session.commit()
    await _achievement(
        session,
        title="Once",
        criteria_type=CriteriaType.total_completions,
        threshold=1,
        points_reward=20,
    )

    chore = await _chore(session, base_points=5)
    first = await complete_chore(session, chore=chore, user=child, settings=settings)
    assert first.already_done is False
    balance_after = await points_balance(session, child.id)
    assert balance_after == 5 + 20  # base + achievement

    second = await complete_chore(session, chore=chore, user=child, settings=settings)
    assert second.already_done is True
    assert second.unlocks == []
    assert await points_balance(session, child.id) == balance_after

    completion_count = await session.scalar(select(func.count()).select_from(ChoreCompletion))
    assert completion_count == 1
    unlock_count = await session.scalar(
        select(func.count()).select_from(UserAchievement).where(UserAchievement.user_id == child.id)
    )
    assert unlock_count == 1


# ---------------------------------------------------------------------------
# Photo policies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_required_photo_fails_without_upload(domain) -> None:
    session, child, settings = domain
    chore = await _chore(session, photo_policy=PhotoPolicy.required)
    with pytest.raises(CompletionError) as exc:
        await complete_chore(session, chore=chore, user=child, settings=settings)
    assert exc.value.code == "photo_required"
    assert await points_balance(session, child.id) == 0
    assert await session.scalar(select(func.count()).select_from(ChoreCompletion)) == 0


@pytest.mark.asyncio
async def test_required_photo_succeeds_with_png(domain) -> None:
    session, child, settings = domain
    await set_setting(session, "early_bonus_points", "0")
    await set_setting(session, "on_time_bonus_points", "0")
    await set_setting(session, "late_bonus_points", "0")
    await session.commit()

    chore = await _chore(session, photo_policy=PhotoPolicy.required, base_points=12)
    result = await complete_chore(
        session,
        chore=chore,
        user=child,
        settings=settings,
        photo=PhotoUpload(data=TINY_PNG, content_type="image/png"),
    )
    assert result.already_done is False
    assert result.completion.photo_object_key is not None
    assert result.completion.photo_object_key.endswith(".png")
    assert await points_balance(session, child.id) == 12


@pytest.mark.asyncio
async def test_optional_photo_succeeds_without_upload(domain) -> None:
    session, child, settings = domain
    await set_setting(session, "early_bonus_points", "0")
    await set_setting(session, "on_time_bonus_points", "0")
    await set_setting(session, "late_bonus_points", "0")
    await session.commit()

    chore = await _chore(session, photo_policy=PhotoPolicy.optional, base_points=9)
    result = await complete_chore(session, chore=chore, user=child, settings=settings)
    assert result.already_done is False
    assert result.completion.photo_object_key is None
    assert await points_balance(session, child.id) == 9


@pytest.mark.asyncio
async def test_optional_photo_saves_when_provided(domain) -> None:
    session, child, settings = domain
    chore = await _chore(session, photo_policy=PhotoPolicy.optional)
    result = await complete_chore(
        session,
        chore=chore,
        user=child,
        settings=settings,
        photo=PhotoUpload(data=TINY_PNG, content_type="image/png"),
    )
    assert result.completion.photo_object_key is not None


@pytest.mark.asyncio
async def test_none_policy_ignores_uploaded_photo(domain) -> None:
    """photo_policy=none never stores a photo even if one is submitted."""
    session, child, settings = domain
    chore = await _chore(session, photo_policy=PhotoPolicy.none)
    result = await complete_chore(
        session,
        chore=chore,
        user=child,
        settings=settings,
        photo=PhotoUpload(data=TINY_PNG, content_type="image/png"),
    )
    assert result.completion.photo_object_key is None


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_total_completions_unlocks_and_awards_points(domain) -> None:
    session, child, settings = domain
    await set_setting(session, "early_bonus_points", "0")
    await set_setting(session, "on_time_bonus_points", "0")
    await set_setting(session, "late_bonus_points", "0")
    await session.commit()
    await _achievement(
        session,
        title="Two Done",
        criteria_type=CriteriaType.total_completions,
        threshold=2,
        points_reward=30,
    )

    c1 = await _chore(session, title="A", base_points=1)
    first = await complete_chore(session, chore=c1, user=child, settings=settings)
    assert first.unlocks == []
    assert await points_balance(session, child.id) == 1

    c2 = await _chore(session, title="B", base_points=1)
    second = await complete_chore(session, chore=c2, user=child, settings=settings)
    assert any(u.achievement.title == "Two Done" for u in second.unlocks)
    assert second.points.achievement_points == 30
    assert await points_balance(session, child.id) == 1 + 1 + 30

    ach_ledger = (
        (
            await session.execute(
                select(PointLedger).where(
                    PointLedger.user_id == child.id,
                    PointLedger.ref_type == "achievement",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(ach_ledger) == 1
    assert ach_ledger[0].delta == 30
    assert "Two Done" in ach_ledger[0].reason


@pytest.mark.asyncio
async def test_on_time_count_achievement(domain) -> None:
    session, child, settings = domain
    await _achievement(
        session,
        title="Punctual",
        criteria_type=CriteriaType.complete_on_time_count,
        threshold=2,
        points_reward=15,
    )
    chore = await _chore(session, base_points=0)
    today = local_today(settings)
    for i in range(2):
        session.add(
            ChoreCompletion(
                chore_id=chore.id,
                user_id=child.id,
                local_date=today - timedelta(days=i + 1),
                completed_at=datetime.now(tz=UTC),
                timing=TimingStatus.on_time,
                points_awarded=0,
            )
        )
    # late completion should not count toward on-time criteria
    session.add(
        ChoreCompletion(
            chore_id=chore.id,
            user_id=child.id,
            local_date=today - timedelta(days=10),
            completed_at=datetime.now(tz=UTC),
            timing=TimingStatus.late,
            points_awarded=0,
        )
    )
    await session.commit()

    unlocks = await evaluate_achievements(session, user_id=child.id, settings=settings)
    await session.commit()
    assert any(u.achievement.title == "Punctual" for u in unlocks)
    assert await points_balance(session, child.id) == 15


@pytest.mark.asyncio
async def test_early_count_achievement(domain) -> None:
    session, child, settings = domain
    await _achievement(
        session,
        title="Early Bird",
        criteria_type=CriteriaType.complete_early_count,
        threshold=1,
        points_reward=8,
    )
    chore = await _chore(session, base_points=0)
    session.add(
        ChoreCompletion(
            chore_id=chore.id,
            user_id=child.id,
            local_date=local_today(settings),
            completed_at=datetime.now(tz=UTC),
            timing=TimingStatus.early,
            points_awarded=0,
        )
    )
    await session.commit()

    unlocks = await evaluate_achievements(session, user_id=child.id, settings=settings)
    await session.commit()
    assert any(u.achievement.title == "Early Bird" for u in unlocks)
    assert await points_balance(session, child.id) == 8


@pytest.mark.asyncio
async def test_photo_completions_require_photo_key(domain) -> None:
    session, child, settings = domain
    await _achievement(
        session,
        title="Snapper",
        criteria_type=CriteriaType.photo_completions,
        threshold=1,
        points_reward=5,
    )
    chore = await _chore(session, base_points=0)
    # Completion without photo must not unlock
    session.add(
        ChoreCompletion(
            chore_id=chore.id,
            user_id=child.id,
            local_date=local_today(settings) - timedelta(days=1),
            completed_at=datetime.now(tz=UTC),
            timing=TimingStatus.on_time,
            photo_object_key=None,
            points_awarded=0,
        )
    )
    await session.commit()
    unlocks = await evaluate_achievements(session, user_id=child.id, settings=settings)
    assert unlocks == []

    session.add(
        ChoreCompletion(
            chore_id=chore.id,
            user_id=child.id,
            local_date=local_today(settings),
            completed_at=datetime.now(tz=UTC),
            timing=TimingStatus.on_time,
            photo_object_key="completions/1/x.png",
            points_awarded=0,
        )
    )
    await session.commit()
    unlocks = await evaluate_achievements(session, user_id=child.id, settings=settings)
    await session.commit()
    assert any(u.achievement.title == "Snapper" for u in unlocks)
    assert await points_balance(session, child.id) == 5


@pytest.mark.asyncio
async def test_inactive_achievement_not_evaluated(domain) -> None:
    session, child, settings = domain
    await _achievement(
        session,
        title="Hidden",
        criteria_type=CriteriaType.total_completions,
        threshold=1,
        points_reward=99,
        is_active=False,
    )
    chore = await _chore(session, base_points=0)
    session.add(
        ChoreCompletion(
            chore_id=chore.id,
            user_id=child.id,
            local_date=local_today(settings),
            completed_at=datetime.now(tz=UTC),
            timing=TimingStatus.on_time,
            points_awarded=0,
        )
    )
    await session.commit()

    unlocks = await evaluate_achievements(session, user_id=child.id, settings=settings)
    await session.commit()
    assert unlocks == []
    assert await points_balance(session, child.id) == 0


@pytest.mark.asyncio
async def test_achievement_unlocks_only_once(domain) -> None:
    session, child, settings = domain
    await _achievement(
        session,
        title="First",
        criteria_type=CriteriaType.total_completions,
        threshold=1,
        points_reward=10,
    )
    chore = await _chore(session, base_points=0)
    session.add(
        ChoreCompletion(
            chore_id=chore.id,
            user_id=child.id,
            local_date=local_today(settings),
            completed_at=datetime.now(tz=UTC),
            timing=TimingStatus.on_time,
            points_awarded=0,
        )
    )
    await session.commit()

    first = await evaluate_achievements(session, user_id=child.id, settings=settings)
    await session.commit()
    assert len(first) == 1
    assert await points_balance(session, child.id) == 10

    second = await evaluate_achievements(session, user_id=child.id, settings=settings)
    await session.commit()
    assert second == []
    assert await points_balance(session, child.id) == 10

    unlock_count = await session.scalar(
        select(func.count()).select_from(UserAchievement).where(UserAchievement.user_id == child.id)
    )
    assert unlock_count == 1


@pytest.mark.asyncio
async def test_zero_reward_achievement_unlocks_without_ledger(domain) -> None:
    session, child, settings = domain
    await _achievement(
        session,
        title="Bragging Rights",
        criteria_type=CriteriaType.total_completions,
        threshold=1,
        points_reward=0,
    )
    chore = await _chore(session, base_points=0)
    session.add(
        ChoreCompletion(
            chore_id=chore.id,
            user_id=child.id,
            local_date=local_today(settings),
            completed_at=datetime.now(tz=UTC),
            timing=TimingStatus.on_time,
            points_awarded=0,
        )
    )
    await session.commit()

    unlocks = await evaluate_achievements(session, user_id=child.id, settings=settings)
    await session.commit()
    assert any(u.achievement.title == "Bragging Rights" for u in unlocks)
    assert await points_balance(session, child.id) == 0
    ledger_count = await session.scalar(select(func.count()).select_from(PointLedger))
    assert ledger_count == 0
    ua = await session.scalar(
        select(func.count()).select_from(UserAchievement).where(UserAchievement.user_id == child.id)
    )
    assert ua == 1


@pytest.mark.asyncio
async def test_points_awarded_column_excludes_achievement_rewards(domain) -> None:
    """ChoreCompletion.points_awarded is base+timing only (issue #10)."""
    session, child, settings = domain
    await set_setting(session, "early_bonus_points", "0")
    await set_setting(session, "on_time_bonus_points", "3")
    await set_setting(session, "late_bonus_points", "0")
    await session.commit()
    await _achievement(
        session,
        title="Bonus Badge",
        criteria_type=CriteriaType.total_completions,
        threshold=1,
        points_reward=50,
    )

    chore = await _chore(session, base_points=10)
    with patch(
        "qr_chores.services.completion.classify_timing",
        return_value=TimingStatus.on_time,
    ):
        result = await complete_chore(session, chore=chore, user=child, settings=settings)

    assert result.completion.points_awarded == 13  # 10 + 3, not +50
    assert result.points.achievement_points == 50
    assert result.points.total == 63
    assert await points_balance(session, child.id) == 63
