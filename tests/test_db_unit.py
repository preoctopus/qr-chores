"""Unit tests for db helpers."""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.db import (
    _engine_kwargs,
    ensure_sqlite_parent_dir,
    get_db,
    init_db,
)


def test_ensure_sqlite_parent_dir_creates(tmp_path: Path) -> None:
    db_file = tmp_path / "nested" / "app.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    ensure_sqlite_parent_dir(url)
    assert db_file.parent.is_dir()


def test_ensure_sqlite_parent_dir_ignores_memory() -> None:
    ensure_sqlite_parent_dir("sqlite+aiosqlite:///:memory:")
    ensure_sqlite_parent_dir("postgresql+asyncpg://u:p@localhost/db")


def test_engine_kwargs_sqlite_and_other() -> None:
    sqlite_kw = _engine_kwargs("sqlite+aiosqlite:///:memory:")
    assert sqlite_kw["echo"] is False
    assert sqlite_kw["connect_args"] == {"check_same_thread": False}

    pg_kw = _engine_kwargs("postgresql+asyncpg://u:p@localhost/db")
    assert pg_kw["echo"] is False
    assert "connect_args" not in pg_kw


@pytest.mark.asyncio
async def test_get_db_yields_session(monkeypatch: pytest.MonkeyPatch, test_settings) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from qr_chores import db as db_module

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(db_module, "SessionLocal", factory)

    gen = get_db()
    session = await gen.__anext__()
    assert isinstance(session, AsyncSession)
    await gen.aclose()
    await engine.dispose()


@pytest.mark.asyncio
async def test_init_db_creates_tables(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    from qr_chores import db as db_module

    db_file = tmp_path / "init" / "test.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    engine = create_async_engine(url, connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_module, "engine", engine)

    await init_db()
    assert db_file.parent.is_dir()
    # second call is fine
    await init_db()
    await engine.dispose()
