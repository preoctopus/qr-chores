"""Shared pytest fixtures."""

from collections.abc import AsyncGenerator, Iterator
from datetime import date, datetime
from datetime import time as time_type
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from qr_chores.auth.passwords import hash_password
from qr_chores.config import Settings, get_settings
from qr_chores.db import Base, get_db
from qr_chores.main import create_app
from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.models.user import User, UserRole
from qr_chores.services.qr import new_qr_token
from qr_chores.services.timeutil import clear_frozen_time, frozen_at


@pytest.fixture(autouse=True)
def _reset_app_clock() -> Iterator[None]:
    """Ensure no test leaves the app clock frozen for another test."""
    clear_frozen_time()
    yield
    clear_frozen_time()


@pytest.fixture
def freeze_app_time(test_settings: Settings):
    """Pin APP_TIMEZONE wall clock: ``with freeze_app_time(date|datetime): ...``."""

    def _freeze(when: datetime | date, *, tz: str | ZoneInfo | None = None):
        return frozen_at(when, tz=tz or test_settings.app_timezone)

    return _freeze


@pytest.fixture
def test_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Settings:
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("APP_TIMEZONE", "America/Chicago")
    monkeypatch.setenv("BASE_URL", "http://testserver")
    monkeypatch.setenv("SEED_PARENT_PASSWORD", "parent-pass")
    monkeypatch.setenv("SEED_CHILD_PASSWORD", "child-pass")
    monkeypatch.setenv("PHOTO_STORAGE", "local")
    monkeypatch.setenv("PHOTO_LOCAL_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    from qr_chores.services.storage import clear_photo_storage_cache

    clear_photo_storage_cache()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()
    clear_photo_storage_cache()


@pytest_asyncio.fixture
async def db_session(test_settings: Settings) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def app(test_settings: Settings):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    application = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_db] = _override_db
    application.state.session_factory = session_factory  # type: ignore[attr-defined]
    application.state.engine = engine  # type: ignore[attr-defined]

    yield application

    application.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def create_user(
    session_factory,
    *,
    email: str,
    display_name: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    password: str,
    role: UserRole,
    parent_id: int | None = None,
) -> User:
    if first_name is None and last_name is None and display_name:
        parts = display_name.strip().split(None, 1)
        first_name = parts[0] if parts else "User"
        last_name = parts[1] if len(parts) > 1 else "Test"
    first_name = first_name or "User"
    last_name = last_name or "Test"
    display = display_name or f"{first_name} {last_name}".strip()
    async with session_factory() as session:
        user = User(
            email=email.lower(),
            first_name=first_name,
            last_name=last_name,
            display_name=display,
            password_hash=hash_password(password),
            role=role,
            parent_id=parent_id,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def parent_user(app) -> User:
    return await create_user(
        app.state.session_factory,
        email="dad@example.com",
        first_name="Dad",
        last_name="Example",
        password="parent-pass",
        role=UserRole.parent,
    )


@pytest_asyncio.fixture
async def child_user(app, parent_user: User) -> User:
    return await create_user(
        app.state.session_factory,
        email="daughter@example.com",
        first_name="Daughter",
        last_name="Example",
        password="child-pass",
        role=UserRole.child,
        parent_id=parent_user.id,
    )


async def create_chore(session_factory, *, assignee_user_id: int | None = None, **kwargs) -> Chore:
    """Insert a chore. Pass assignee_user_id for parent-scoped boards."""
    defaults = {
        "title": "Test chore",
        "description": None,
        "qr_token": new_qr_token(),
        "due_time": time_type(20, 0),
        "schedule_days": "0123456",
        "photo_policy": PhotoPolicy.none,
        "base_points": 10,
        "is_active": True,
        "assignee_user_id": assignee_user_id,
    }
    defaults.update(kwargs)
    async with session_factory() as session:
        chore = Chore(**defaults)
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        return chore
