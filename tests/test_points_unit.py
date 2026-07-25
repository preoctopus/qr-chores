"""Unit tests for points helpers."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from qr_chores.db import Base
from qr_chores.services.points import (
    DEFAULT_BONUSES,
    add_ledger_entry,
    get_setting,
    get_timing_bonuses,
    points_balance,
    set_setting,
)


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_settings_and_bonuses(session: AsyncSession) -> None:
    assert await get_setting(session, "missing", "fallback") == "fallback"
    await set_setting(session, "early_bonus_points", "11")
    await session.commit()
    assert await get_setting(session, "early_bonus_points") == "11"
    # update existing
    await set_setting(session, "early_bonus_points", "3")
    await session.commit()
    bonuses = await get_timing_bonuses(session)
    assert bonuses["early_bonus_points"] == 3
    assert "on_time_bonus_points" in bonuses
    assert set(DEFAULT_BONUSES) <= set(bonuses)

    # invalid stored value falls back to default
    await set_setting(session, "on_time_bonus_points", "not-a-number")
    await session.commit()
    bonuses2 = await get_timing_bonuses(session)
    assert bonuses2["on_time_bonus_points"] == int(DEFAULT_BONUSES["on_time_bonus_points"])


@pytest.mark.asyncio
async def test_ledger_balance(session: AsyncSession) -> None:
    # user_id FK may not be enforced as strictly on sqlite without user row depending
    # on pragma — create a user first
    from qr_chores.auth.passwords import hash_password
    from qr_chores.models.user import User, UserRole

    user = User(
        email="pts@example.com",
        display_name="Pts",
        password_hash=hash_password("x"),
        role=UserRole.child,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    assert await points_balance(session, user.id) == 0
    assert add_ledger_entry(session, user_id=user.id, delta=0, reason="noop") is None
    add_ledger_entry(session, user_id=user.id, delta=10, reason="base")
    add_ledger_entry(session, user_id=user.id, delta=5, reason="bonus")
    await session.commit()
    assert await points_balance(session, user.id) == 15
