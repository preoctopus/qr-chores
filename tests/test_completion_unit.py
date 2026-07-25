"""Unit tests for completion domain rules."""

from datetime import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from qr_chores.auth.passwords import hash_password
from qr_chores.config import Settings
from qr_chores.db import Base
from qr_chores.models.chore import Chore, PhotoPolicy, TimingStatus
from qr_chores.models.user import User, UserRole
from qr_chores.services.completion import (
    CompletionError,
    PhotoUpload,
    complete_chore,
)
from qr_chores.services.qr import new_qr_token


@pytest.fixture
async def ctx(tmp_path):
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
            email="c@example.com",
            display_name="C",
            password_hash=hash_password("x"),
            role=UserRole.child,
            is_active=True,
        )
        session.add(child)
        await session.commit()
        await session.refresh(child)
        yield session, child, settings
    await engine.dispose()


async def _chore(session, **kwargs) -> Chore:
    defaults = {
        "title": "X",
        "qr_token": new_qr_token(),
        "due_time": time(23, 59),
        "schedule_days": "0123456",
        "photo_policy": PhotoPolicy.none,
        "base_points": 4,
        "is_active": True,
    }
    defaults.update(kwargs)
    chore = Chore(**defaults)
    session.add(chore)
    await session.commit()
    await session.refresh(chore)
    return chore


@pytest.mark.asyncio
async def test_inactive_chore_rejected(ctx) -> None:
    session, child, settings = ctx
    chore = await _chore(session, is_active=False)
    with pytest.raises(CompletionError) as exc:
        await complete_chore(session, chore=chore, user=child, settings=settings)
    assert exc.value.code == "inactive"


@pytest.mark.asyncio
async def test_not_scheduled_rejected(ctx) -> None:
    session, child, settings = ctx
    # empty schedule never matches
    chore = await _chore(session, schedule_days="")
    with pytest.raises(CompletionError) as exc:
        await complete_chore(session, chore=chore, user=child, settings=settings)
    assert exc.value.code == "not_scheduled"


@pytest.mark.asyncio
async def test_required_photo_and_success(ctx) -> None:
    session, child, settings = ctx
    chore = await _chore(session, photo_policy=PhotoPolicy.required, base_points=6)
    with pytest.raises(CompletionError) as exc:
        await complete_chore(session, chore=chore, user=child, settings=settings)
    assert exc.value.code == "photo_required"

    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    result = await complete_chore(
        session,
        chore=chore,
        user=child,
        settings=settings,
        photo=PhotoUpload(data=png, content_type="image/png"),
    )
    assert result.already_done is False
    assert result.completion.photo_object_key is not None
    assert result.points.base == 6
    assert result.completion.timing in {
        TimingStatus.early,
        TimingStatus.on_time,
        TimingStatus.late,
    }

    again = await complete_chore(session, chore=chore, user=child, settings=settings)
    assert again.already_done is True
