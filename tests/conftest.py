"""Shared pytest fixtures."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from qr_chores.auth.passwords import hash_password
from qr_chores.config import Settings, get_settings
from qr_chores.db import Base, get_db
from qr_chores.main import create_app
from qr_chores.models.user import User, UserRole


@pytest.fixture
def test_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Settings:
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("APP_TIMEZONE", "America/Chicago")
    monkeypatch.setenv("BASE_URL", "http://testserver")
    monkeypatch.setenv("SEED_PARENT_PASSWORD", "parent-pass")
    monkeypatch.setenv("SEED_CHILD_PASSWORD", "child-pass")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_session(test_settings: Settings) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def app(test_settings: Settings):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
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
    display_name: str,
    password: str,
    role: UserRole,
) -> User:
    async with session_factory() as session:
        user = User(
            email=email.lower(),
            display_name=display_name,
            password_hash=hash_password(password),
            role=role,
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
        display_name="Dad",
        password="parent-pass",
        role=UserRole.parent,
    )


@pytest_asyncio.fixture
async def child_user(app) -> User:
    return await create_user(
        app.state.session_factory,
        email="daughter@example.com",
        display_name="Daughter",
        password="child-pass",
        role=UserRole.child,
    )
