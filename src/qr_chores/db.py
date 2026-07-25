"""Async SQLAlchemy engine and session helpers."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from qr_chores.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    kwargs: dict = {"echo": False}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


settings = get_settings()
engine = create_async_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def ensure_sqlite_parent_dir(url: str) -> None:
    """Create parent directory for file-backed SQLite databases."""
    if not url.startswith("sqlite") or "///" not in url:
        return
    raw = url.split("///", 1)[-1]
    if not raw or raw.startswith(":memory:"):
        return
    from pathlib import Path

    Path(raw).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


async def init_db() -> None:
    """Create tables (dev/test convenience). Prefer Alembic in production."""
    from qr_chores import models  # noqa: F401

    ensure_sqlite_parent_dir(str(engine.url))

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
