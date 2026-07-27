"""Seed script tests."""

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from qr_chores.auth.passwords import verify_password
from qr_chores.config import Settings, get_settings
from qr_chores.db import Base
from qr_chores.models.user import User, UserRole
from qr_chores.seed import DEFAULT_USERS, main, seed


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


@pytest.mark.asyncio
async def test_seed_creates_sqlite_parent_dir(
    test_settings: Settings, monkeypatch, tmp_path: Path
) -> None:
    from qr_chores import db as db_module

    db_file = tmp_path / "seed-data" / "app.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()

    engine = create_async_engine(url, connect_args={"check_same_thread": False})
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _init() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", session_factory)
    monkeypatch.setattr("qr_chores.seed.init_db", _init)
    monkeypatch.setattr("qr_chores.seed.SessionLocal", session_factory)

    await seed()
    assert db_file.parent.is_dir()
    await engine.dispose()
    get_settings.cache_clear()


def test_seed_main_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom() -> None:
        raise RuntimeError("seed explode")

    monkeypatch.setattr("qr_chores.seed.seed", _boom)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
