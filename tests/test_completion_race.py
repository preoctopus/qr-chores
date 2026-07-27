"""Concurrent complete + IntegrityError recovery (unique chore_id+local_date)."""

from __future__ import annotations

import asyncio
from datetime import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from qr_chores.auth.passwords import hash_password
from qr_chores.config import Settings
from qr_chores.db import Base
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy
from qr_chores.models.rewards import PointLedger
from qr_chores.models.user import User, UserRole
from qr_chores.services.completion import (
    CompletionError,
    PhotoUpload,
    complete_chore,
)
from qr_chores.services.points import points_balance, set_setting
from qr_chores.services.qr import new_qr_token
from qr_chores.services.storage import StorageError

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _build_ctx(tmp_path: Path, *, db_name: str = "race.db"):
    """File-backed SQLite so concurrent sessions share one DB."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / db_name}",
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
            email="racer@example.com",
            display_name="Racer",
            password_hash=hash_password("x"),
            role=UserRole.child,
            is_active=True,
        )
        session.add(child)
        await set_setting(session, "early_bonus_points", "0")
        await set_setting(session, "on_time_bonus_points", "0")
        await set_setting(session, "late_bonus_points", "0")
        await session.commit()
        await session.refresh(child)
        child_id = child.id

    return engine, factory, settings, child_id


async def _add_chore(factory, **kwargs) -> int:
    defaults = {
        "title": "Race chore",
        "qr_token": new_qr_token(),
        "due_time": time(23, 59),
        "schedule_days": "0123456",
        "photo_policy": PhotoPolicy.none,
        "base_points": 10,
        "is_active": True,
    }
    defaults.update(kwargs)
    async with factory() as session:
        chore = Chore(**defaults)
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        return chore.id


@pytest.mark.asyncio
async def test_integrity_error_returns_already_done_and_cleans_orphan_photo(
    tmp_path: Path,
) -> None:
    """Losing racer: UNIQUE violation → already_done; orphan photo file deleted.

    Simulates the race window where both racers saw no completion, then the
    second flush hits uq_chore_completion_day.
    """
    engine, factory, settings, child_id = await _build_ctx(tmp_path, db_name="ie.db")
    chore_id = await _add_chore(
        factory,
        photo_policy=PhotoPolicy.required,
        base_points=12,
    )

    # Winner completes first (with photo)
    async with factory() as session:
        child = await session.get(User, child_id)
        chore = await session.get(Chore, chore_id)
        assert child and chore
        winner = await complete_chore(
            session,
            chore=chore,
            user=child,
            settings=settings,
            photo=PhotoUpload(data=TINY_PNG, content_type="image/png"),
        )
        assert winner.already_done is False
        winner_key = winner.completion.photo_object_key
        assert winner_key
        winner_id = winner.completion.id

    # Loser: pretend first existence check missed the winner (race window).
    # Real UNIQUE on flush then triggers IntegrityError recovery.
    async with factory() as session:
        child = await session.get(User, child_id)
        chore = await session.get(Chore, chore_id)
        assert child and chore

        deleted_keys: list[str] = []
        from qr_chores.services.storage import get_photo_storage

        real_storage = get_photo_storage(settings)

        class TrackingStorage:
            def save(self, key, data, content_type):
                return real_storage.save(key, data, content_type)

            def open(self, key):
                return real_storage.open(key)

            def delete(self, key):
                deleted_keys.append(key)
                real_storage.delete(key)

        get_calls = {"n": 0}

        async def _get_side_effect(db, c, s):
            get_calls["n"] += 1
            if get_calls["n"] == 1:
                return None  # race window: both thought the day was free
            result = await db.execute(
                select(ChoreCompletion).where(ChoreCompletion.chore_id == chore_id)
            )
            return result.scalar_one()

        with (
            patch(
                "qr_chores.services.completion.get_completion_for_today",
                side_effect=_get_side_effect,
            ),
            patch(
                "qr_chores.services.completion.get_photo_storage",
                return_value=TrackingStorage(),
            ),
        ):
            loser = await complete_chore(
                session,
                chore=chore,
                user=child,
                settings=settings,
                photo=PhotoUpload(data=TINY_PNG, content_type="image/png"),
            )

        assert loser.already_done is True
        assert loser.completion.id == winner_id
        # Orphan photo from loser's upload was deleted
        assert len(deleted_keys) == 1
        assert deleted_keys[0] != winner_key
        # Winner's photo still readable
        data, _ = real_storage.open(winner_key)
        assert data == TINY_PNG

    async with factory() as session:
        assert await points_balance(session, child_id) == 12
        assert await session.scalar(select(func.count()).select_from(ChoreCompletion)) == 1
        ledger_n = await session.scalar(
            select(func.count()).select_from(PointLedger).where(PointLedger.user_id == child_id)
        )
        assert ledger_n == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_integrity_error_without_existing_raises_db_error(tmp_path: Path) -> None:
    """If UNIQUE fails but no row is found after rollback, surface CompletionError."""
    engine, factory, settings, child_id = await _build_ctx(tmp_path, db_name="ie2.db")
    chore_id = await _add_chore(factory)

    async with factory() as session:
        child = await session.get(User, child_id)
        chore = await session.get(Chore, chore_id)
        assert child and chore

        with (
            patch(
                "qr_chores.services.completion.get_completion_for_today",
                return_value=None,
            ),
            patch.object(
                session,
                "flush",
                side_effect=IntegrityError("stmt", "params", Exception("uq")),
            ),
        ):
            with pytest.raises(CompletionError) as exc:
                await complete_chore(session, chore=chore, user=child, settings=settings)
            assert exc.value.code == "db"

    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_complete_awards_once(tmp_path: Path) -> None:
    """Two parallel complete_chore calls → one winner, one already_done, one ledger row."""
    engine, factory, settings, child_id = await _build_ctx(tmp_path, db_name="concurrent.db")
    chore_id = await _add_chore(factory, base_points=15)

    async def _race() -> tuple[bool, int]:
        async with factory() as session:
            child = await session.get(User, child_id)
            chore = await session.get(Chore, chore_id)
            assert child and chore
            result = await complete_chore(session, chore=chore, user=child, settings=settings)
            return result.already_done, result.completion.id

    outcomes = await asyncio.gather(_race(), _race(), _race())
    already = [o[0] for o in outcomes]
    completion_ids = {o[1] for o in outcomes}

    assert sum(1 for a in already if not a) == 1, outcomes
    assert sum(1 for a in already if a) == 2, outcomes
    assert len(completion_ids) == 1

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ChoreCompletion)) == 1
        assert await points_balance(session, child_id) == 15
        assert (
            await session.scalar(
                select(func.count()).select_from(PointLedger).where(PointLedger.user_id == child_id)
            )
        ) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_http_complete_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parallel HTTP POSTs to /api/v1 complete share UNIQUE constraint — one award."""
    from httpx import ASGITransport, AsyncClient

    from qr_chores.config import get_settings
    from qr_chores.db import get_db
    from qr_chores.main import create_app
    from qr_chores.services.storage import clear_photo_storage_cache

    db_file = tmp_path / "http_race.db"
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setenv("APP_TIMEZONE", "America/Chicago")
    monkeypatch.setenv("BASE_URL", "http://testserver")
    monkeypatch.setenv("PHOTO_STORAGE", "local")
    monkeypatch.setenv("PHOTO_LOCAL_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    clear_photo_storage_cache()

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as session:
        child = User(
            email="http-racer@example.com",
            display_name="HttpRacer",
            password_hash=hash_password("child-pass"),
            role=UserRole.child,
            is_active=True,
        )
        session.add(child)
        await set_setting(session, "early_bonus_points", "0")
        await set_setting(session, "on_time_bonus_points", "0")
        await set_setting(session, "late_bonus_points", "0")
        chore = Chore(
            title="HTTP race",
            qr_token=new_qr_token(),
            due_time=time(23, 59),
            schedule_days="0123456",
            photo_policy=PhotoPolicy.none,
            base_points=20,
            is_active=True,
        )
        session.add(chore)
        await session.commit()
        await session.refresh(child)
        await session.refresh(chore)
        child_id = child.id
        qr_token = chore.qr_token

    application = create_app()

    async def _override_db():
        async with factory() as session:
            yield session

    application.dependency_overrides[get_db] = _override_db

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "http-racer@example.com", "password": "child-pass"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        async def _post():
            return await client.post(f"/api/v1/c/{qr_token}/complete", headers=headers)

        responses = await asyncio.gather(_post(), _post(), _post())

    statuses = [r.status_code for r in responses]
    assert all(s == 200 for s in statuses), statuses
    bodies = [r.json() for r in responses]
    winners = [b for b in bodies if b["already_done"] is False]
    losers = [b for b in bodies if b["already_done"] is True]
    assert len(winners) == 1, bodies
    assert len(losers) == 2, bodies
    assert winners[0]["points"]["base"] == 20

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ChoreCompletion)) == 1
        assert await points_balance(session, child_id) == 20

    application.dependency_overrides.clear()
    await engine.dispose()
    get_settings.cache_clear()
    clear_photo_storage_cache()


@pytest.mark.asyncio
async def test_integrity_error_photo_delete_storage_error_suppressed(tmp_path: Path) -> None:
    """StorageError during orphan photo cleanup must not mask already_done recovery."""
    engine, factory, settings, child_id = await _build_ctx(tmp_path, db_name="ie3.db")
    chore_id = await _add_chore(factory, photo_policy=PhotoPolicy.optional, base_points=5)

    async with factory() as session:
        child = await session.get(User, child_id)
        chore = await session.get(Chore, chore_id)
        assert child and chore
        winner = await complete_chore(session, chore=chore, user=child, settings=settings)
        assert winner.already_done is False

    async with factory() as session:
        child = await session.get(User, child_id)
        chore = await session.get(Chore, chore_id)
        assert child and chore

        mock_storage = MagicMock()
        mock_storage.save.return_value = MagicMock(
            key="orphan.png", content_type="image/png", size=1
        )
        mock_storage.delete.side_effect = StorageError("boom", "storage")

        call_n = {"n": 0}

        async def _get(db, c, s):
            call_n["n"] += 1
            if call_n["n"] == 1:
                return None
            result = await db.execute(
                select(ChoreCompletion).where(ChoreCompletion.chore_id == chore_id)
            )
            return result.scalar_one()

        with (
            patch("qr_chores.services.completion.get_completion_for_today", side_effect=_get),
            patch("qr_chores.services.completion.get_photo_storage", return_value=mock_storage),
            patch(
                "qr_chores.services.completion.validate_and_build_key",
                return_value=("orphan.png", "image/png"),
            ),
        ):
            # Real UNIQUE on flush after winner already inserted; StorageError on delete
            # must still recover already_done.
            result = await complete_chore(
                session,
                chore=chore,
                user=child,
                settings=settings,
                photo=PhotoUpload(data=TINY_PNG, content_type="image/png"),
            )

        assert result.already_done is True
        mock_storage.delete.assert_called_once_with("orphan.png")

    await engine.dispose()
