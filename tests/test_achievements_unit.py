"""Unit tests for achievement criteria helpers."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from qr_chores.config import Settings
from qr_chores.db import Base
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy, TimingStatus
from qr_chores.models.rewards import Achievement, CriteriaType
from qr_chores.models.user import User, UserRole
from qr_chores.services.achievements import (
    _streak_days,
    criteria_threshold,
    ensure_default_achievements,
    progress_for,
)
from qr_chores.services.timeutil import local_today


def test_criteria_threshold_parses() -> None:
    ach = Achievement(
        title="t",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.streak_days,
        criteria_json='{"days": 4}',
        points_reward=1,
    )
    assert criteria_threshold(ach) == 4

    ach2 = Achievement(
        title="t",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.total_completions,
        criteria_json="not-json",
        points_reward=1,
    )
    assert criteria_threshold(ach2) == 1


def test_criteria_threshold_streak_prefers_days_over_count() -> None:
    """When both keys are present, streak uses days; other types use count."""
    streak = Achievement(
        title="t",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.streak_days,
        criteria_json='{"days": 7, "count": 2}',
        points_reward=1,
    )
    assert criteria_threshold(streak) == 7

    total = Achievement(
        title="t",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.total_completions,
        criteria_json='{"days": 7, "count": 2}',
        points_reward=1,
    )
    assert criteria_threshold(total) == 2


def test_criteria_threshold_fallback_keys() -> None:
    streak_via_count = Achievement(
        title="t",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.streak_days,
        criteria_json='{"count": 5}',
        points_reward=1,
    )
    assert criteria_threshold(streak_via_count) == 5

    total_via_days = Achievement(
        title="t",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.total_completions,
        criteria_json='{"days": 9}',
        points_reward=1,
    )
    assert criteria_threshold(total_via_days) == 9


@pytest.mark.asyncio
async def test_ensure_defaults_idempotent() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        n1 = await ensure_default_achievements(session)
        await session.commit()
        n2 = await ensure_default_achievements(session)
        await session.commit()
        assert n1 == 6
        assert n2 == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_progress_zero_without_data() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    settings = Settings(app_timezone="UTC")
    async with factory() as session:
        ach = Achievement(
            title="T",
            description="",
            icon_key="star",
            criteria_type=CriteriaType.photo_completions,
            criteria_json=json.dumps({"count": 3}),
            points_reward=1,
            is_active=True,
        )
        session.add(ach)
        await session.commit()
        await session.refresh(ach)
        assert await progress_for(session, user_id=999, achievement=ach, settings=settings) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_streak_days_calculation() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    settings = Settings(app_timezone="UTC")

    async with factory() as session:
        user = User(
            email="child@example.com",
            display_name="Child",
            password_hash="hash",
            role=UserRole.child,
        )
        chore = Chore(
            title="Clean Room",
            qr_token="token123",
            due_time=datetime.now(tz=UTC).time(),
            schedule_days="0123456",
            photo_policy=PhotoPolicy.none,
            base_points=10,
        )
        session.add_all([user, chore])
        await session.flush()

        today = local_today(settings)

        # Insert completions for 3 days ending yesterday (today - 3, today - 2, today - 1)
        for days_ago in (3, 2, 1):
            session.add(
                ChoreCompletion(
                    chore_id=chore.id,
                    user_id=user.id,
                    local_date=today - timedelta(days=days_ago),
                    completed_at=datetime.now(tz=UTC),
                    timing=TimingStatus.on_time,
                    points_awarded=10,
                )
            )
        await session.commit()

        # Completed yesterday, nothing today -> streak should show prior 3-day streak
        streak_yesterday = await _streak_days(session, user.id, settings)
        assert streak_yesterday == 3

        # Add completion for today
        session.add(
            ChoreCompletion(
                chore_id=chore.id,
                user_id=user.id,
                local_date=today,
                completed_at=datetime.now(tz=UTC),
                timing=TimingStatus.on_time,
                points_awarded=10,
            )
        )
        await session.commit()

        # Completed today -> streak should include today and be 4
        streak_today = await _streak_days(session, user.id, settings)
        assert streak_today == 4

        # Also verify via progress_for helper
        ach = Achievement(
            title="Streak Ach",
            description="",
            icon_key="fire",
            criteria_type=CriteriaType.streak_days,
            criteria_json=json.dumps({"days": 3}),
            points_reward=10,
        )
        session.add(ach)
        await session.commit()
        assert await progress_for(session, user.id, ach, settings) == 4

    await engine.dispose()
