"""Unit tests for today_board and list helpers."""

from datetime import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from qr_chores.config import Settings
from qr_chores.db import Base
from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.services.chores import list_active_chores, list_all_chores, today_board
from qr_chores.services.qr import new_qr_token
from qr_chores.services.timeutil import local_now


@pytest.fixture
async def board_ctx(tmp_path):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    settings = Settings(
        secret_key="test-secret-key",
        app_timezone="America/Chicago",
        photo_storage="local",
        photo_local_dir=str(tmp_path / "uploads"),
        on_time_grace_minutes=15,
    )
    async with factory() as session:
        yield session, settings
    await engine.dispose()


async def _add_chore(session: AsyncSession, **kwargs) -> Chore:
    defaults = {
        "title": "Board chore",
        "qr_token": new_qr_token(),
        "due_time": time(0, 0),  # early morning → often late-pending later in day
        "schedule_days": "0123456",
        "photo_policy": PhotoPolicy.none,
        "base_points": 5,
        "is_active": True,
    }
    defaults.update(kwargs)
    chore = Chore(**defaults)
    session.add(chore)
    await session.commit()
    await session.refresh(chore)
    return chore


@pytest.mark.asyncio
async def test_today_board_empty_when_no_scheduled(board_ctx) -> None:
    session, settings = board_ctx
    await _add_chore(session, schedule_days="", title="Never")
    board = await today_board(session, settings)
    assert board == []


@pytest.mark.asyncio
async def test_today_board_pending_and_late(board_ctx) -> None:
    session, settings = board_ctx
    # Due at 00:00 local → past grace almost all day → late pending
    await _add_chore(session, title="Midnight due", due_time=time(0, 0))
    # Due near end of day → still pending (not late) for most test runs
    await _add_chore(session, title="Late night", due_time=time(23, 59))
    board = await today_board(session, settings)
    titles = {row.chore.title: row for row in board}
    assert "Midnight due" in titles
    assert "Late night" in titles
    # At least the midnight chore should be late-pending if now is past 00:15
    now = local_now(settings)
    if now.hour > 0 or now.minute > 15:
        assert titles["Midnight due"].is_late_pending is True
        assert titles["Midnight due"].status_kind == "late"
    assert titles["Late night"].done is False


@pytest.mark.asyncio
async def test_list_active_and_all(board_ctx) -> None:
    session, settings = board_ctx
    await _add_chore(session, title="Active one", is_active=True)
    await _add_chore(session, title="Inactive one", is_active=False)
    active = await list_active_chores(session)
    assert all(c.is_active for c in active)
    assert any(c.title == "Active one" for c in active)
    assert not any(c.title == "Inactive one" for c in active)

    all_chores = await list_all_chores(session, include_inactive=True)
    assert len(all_chores) == 2
    active_only = await list_all_chores(session, include_inactive=False)
    assert len(active_only) == 1
