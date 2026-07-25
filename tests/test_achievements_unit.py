"""Unit tests for achievement criteria helpers."""

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from qr_chores.config import Settings
from qr_chores.db import Base
from qr_chores.models.rewards import Achievement, CriteriaType
from qr_chores.services.achievements import (
    _criteria_threshold,
    ensure_default_achievements,
    progress_for,
)


def test_criteria_threshold_parses() -> None:
    ach = Achievement(
        title="t",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.streak_days,
        criteria_json='{"days": 4}',
        points_reward=1,
    )
    assert _criteria_threshold(ach) == 4

    ach2 = Achievement(
        title="t",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.total_completions,
        criteria_json="not-json",
        points_reward=1,
    )
    assert _criteria_threshold(ach2) == 1


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
