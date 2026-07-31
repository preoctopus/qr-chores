"""Fixtures for Playwright End-to-End (E2E) UI tests."""

import asyncio
import concurrent.futures
import os
import socket
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import qr_chores.db
import qr_chores.models  # noqa: F401
from qr_chores.auth.passwords import hash_password
from qr_chores.config import get_settings
from qr_chores.db import Base
from qr_chores.main import create_app
from qr_chores.models.user import User, UserRole
from qr_chores.services.storage import clear_photo_storage_cache


def run_async(coro: Any) -> Any:
    """Helper to run coroutine safely from sync context whether an event loop is running or not."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()
    return asyncio.run(coro)


def find_free_port() -> int:
    """Find an unused TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def seed_e2e_db(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """Seed initial parent/child test users in the database."""
    async with session_factory() as session:
        parent = User(
            email="parent@example.com",
            first_name="Parent",
            last_name="User",
            display_name="Parent User",
            password_hash=hash_password("ParentPassword123!"),
            role=UserRole.parent,
            is_active=True,
        )
        session.add(parent)
        await session.commit()
        await session.refresh(parent)

        child = User(
            email="child@example.com",
            first_name="Child",
            last_name="User",
            display_name="Child User",
            password_hash=hash_password("ChildPassword123!"),
            role=UserRole.child,
            parent_id=parent.id,
            is_active=True,
        )
        session.add(child)
        await session.commit()
        await session.refresh(child)

        return {
            "parent_id": parent.id,
            "child_id": child.id,
        }


async def reset_db_state() -> None:
    """Drop and recreate all database tables and seed initial users."""
    async with qr_chores.db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_e2e_db(qr_chores.db.SessionLocal)


class ServerThread(threading.Thread):
    """Daemon thread for running Uvicorn server in background."""

    def __init__(self, app: Any, host: str, port: int) -> None:
        super().__init__(daemon=True)
        self.config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(config=self.config)

    def run(self) -> None:
        self.server.run()

    def stop(self) -> None:
        self.server.should_exit = True


@pytest.fixture(scope="session")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Generator[str, None, None]:
    """Start live FastAPI application server on a free port for E2E testing."""
    tmp_dir: Path = tmp_path_factory.mktemp("e2e_server")
    db_file = tmp_dir / "e2e_test.db"
    uploads_dir = tmp_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    db_url = f"sqlite+aiosqlite:///{db_file}"
    port = find_free_port()
    host = "127.0.0.1"
    base_url = f"http://{host}:{port}"

    # Configure environment
    os.environ["DATABASE_URL"] = db_url
    os.environ["SECRET_KEY"] = "e2e-secret-key-for-testing-only-12345"
    os.environ["ENVIRONMENT"] = "development"
    os.environ["APP_TIMEZONE"] = "America/Chicago"
    os.environ["BASE_URL"] = base_url
    os.environ["PHOTO_STORAGE"] = "local"
    os.environ["PHOTO_LOCAL_DIR"] = str(uploads_dir)

    get_settings.cache_clear()
    clear_photo_storage_cache()

    # Rebind DB engine & SessionLocal to the test database URL
    new_settings = get_settings()
    qr_chores.db.settings = new_settings
    qr_chores.db.engine = create_async_engine(db_url, **qr_chores.db._engine_kwargs(db_url))
    qr_chores.db.SessionLocal = async_sessionmaker(
        qr_chores.db.engine, class_=AsyncSession, expire_on_commit=False
    )

    # Initialize DB schema & seed data
    run_async(reset_db_state())

    # Create FastAPI app
    app = create_app()

    # Start Uvicorn server in background thread
    server_thread = ServerThread(app=app, host=host, port=port)
    server_thread.start()

    # Wait for server to accept HTTP requests
    import urllib.request

    health_url = f"{base_url}/healthz"
    started = False
    for _ in range(50):
        try:
            with urllib.request.urlopen(health_url, timeout=1) as resp:
                if resp.status == 200:
                    started = True
                    break
        except Exception:
            time.sleep(0.1)

    if not started:
        raise RuntimeError("Failed to start E2E test server")

    yield base_url

    # Stop server
    server_thread.stop()
    server_thread.join(timeout=5)


@pytest.fixture(autouse=True)
def _reset_e2e_db(live_server: str) -> None:
    """Reset database to a clean state before each E2E test."""
    run_async(reset_db_state())


@pytest.fixture(scope="session")
def base_url(live_server: str) -> str:
    """Provide base_url fixture to pytest-playwright."""
    return live_server
