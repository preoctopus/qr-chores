"""Seed script tests."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from qr_chores.auth.passwords import verify_password
from qr_chores.config import Settings
from qr_chores.db import Base
from qr_chores.models.user import User, UserRole
from qr_chores.seed import DEFAULT_USERS, seed


@pytest.mark.asyncio
async def test_seed_creates_three_users(test_settings: Settings, monkeypatch) -> None:
    from qr_chores import db as db_module

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", session_factory)

    # init_db is a no-op create_all against same engine
    async def _noop_init() -> None:
        return None

    monkeypatch.setattr(db_module, "init_db", _noop_init)
    monkeypatch.setattr("qr_chores.seed.init_db", _noop_init)
    monkeypatch.setattr("qr_chores.seed.SessionLocal", session_factory)

    await seed()
    await seed()  # idempotent

    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(User))
        assert count == 3
        parents = (
            (await session.execute(select(User).where(User.role == UserRole.parent)))
            .scalars()
            .all()
        )
        children = (
            (await session.execute(select(User).where(User.role == UserRole.child))).scalars().all()
        )
        assert len(parents) == 2
        assert len(children) == 1
        assert len(DEFAULT_USERS) == 3
        child = children[0]
        assert verify_password(test_settings.seed_child_password, child.password_hash)

    await engine.dispose()
