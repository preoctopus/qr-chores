"""Unit tests for proof photo reaping."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from qr_chores.auth.passwords import hash_password
from qr_chores.config import Settings
from qr_chores.db import Base
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy, TimingStatus
from qr_chores.models.user import User, UserRole
from qr_chores.services.photo_reap import count_reap_candidates, reap_old_photos
from qr_chores.services.qr import new_qr_token
from qr_chores.services.storage import LocalPhotoStorage, clear_photo_storage_cache
from qr_chores.services.timeutil import frozen_at

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

TZ = ZoneInfo("America/Chicago")
# "Today" for reaping tests
TODAY = date(2026, 7, 29)


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
        photo_retention_days=90,
    )
    clear_photo_storage_cache()
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
        yield session, child, settings, tmp_path
    await engine.dispose()
    clear_photo_storage_cache()


async def _chore(session: AsyncSession, child: User) -> Chore:
    chore = Chore(
        title="X",
        qr_token=new_qr_token(),
        due_time=time(20, 0),
        schedule_days="0123456",
        photo_policy=PhotoPolicy.optional,
        base_points=5,
        is_active=True,
        assignee_user_id=child.id,
    )
    session.add(chore)
    await session.commit()
    await session.refresh(chore)
    return chore


async def _completion_with_photo(
    session: AsyncSession,
    *,
    chore: Chore,
    child: User,
    settings: Settings,
    local_date: date,
    key: str | None = None,
) -> ChoreCompletion:
    from pathlib import Path

    store = LocalPhotoStorage(Path(settings.photo_local_dir))
    object_key = key or f"completions/{chore.id}/{local_date.isoformat()}/proof.png"
    store.save(object_key, TINY_PNG, "image/png")
    row = ChoreCompletion(
        chore_id=chore.id,
        user_id=child.id,
        local_date=local_date,
        completed_at=datetime(local_date.year, local_date.month, local_date.day, 12, 0, tzinfo=TZ),
        timing=TimingStatus.on_time,
        photo_object_key=object_key,
        had_photo=True,
        points_awarded=5,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@pytest.mark.asyncio
async def test_reap_disabled_when_retention_nonpositive(ctx) -> None:
    session, child, settings, _tmp = ctx
    settings.photo_retention_days = 0
    with frozen_at(TODAY, tz=TZ):
        result = await reap_old_photos(session, settings)
    assert result.skipped is True
    assert result.candidates == 0


@pytest.mark.asyncio
async def test_reap_dry_run_does_not_delete(ctx) -> None:
    session, child, settings, tmp_path = ctx
    chore = await _chore(session, child)
    old = TODAY - timedelta(days=100)
    row = await _completion_with_photo(
        session, chore=chore, child=child, settings=settings, local_date=old
    )
    path = tmp_path / "uploads" / row.photo_object_key  # type: ignore[operator]
    assert path.is_file()

    with frozen_at(TODAY, tz=TZ):
        result = await reap_old_photos(session, settings, dry_run=True)
    assert result.dry_run is True
    assert result.candidates == 1
    assert result.deleted == 0
    assert result.cleared_keys == 0
    await session.refresh(row)
    assert row.photo_object_key is not None
    assert path.is_file()


@pytest.mark.asyncio
async def test_reap_deletes_old_keeps_recent(ctx) -> None:
    session, child, settings, tmp_path = ctx
    chore = await _chore(session, child)
    old = TODAY - timedelta(days=100)
    recent = TODAY - timedelta(days=10)
    old_row = await _completion_with_photo(
        session,
        chore=chore,
        child=child,
        settings=settings,
        local_date=old,
        key=f"completions/{chore.id}/{old.isoformat()}/old.png",
    )
    # Second completion needs different chore (unique chore_id+local_date)
    chore2 = await _chore(session, child)
    recent_row = await _completion_with_photo(
        session,
        chore=chore2,
        child=child,
        settings=settings,
        local_date=recent,
        key=f"completions/{chore2.id}/{recent.isoformat()}/new.png",
    )
    old_path = tmp_path / "uploads" / old_row.photo_object_key  # type: ignore[operator]
    new_path = tmp_path / "uploads" / recent_row.photo_object_key  # type: ignore[operator]
    assert old_path.is_file() and new_path.is_file()

    with frozen_at(TODAY, tz=TZ):
        assert await count_reap_candidates(session, settings) == 1
        result = await reap_old_photos(session, settings, retention_days=90)

    assert result.candidates == 1
    assert result.deleted == 1
    assert result.cleared_keys == 1
    assert result.failed == 0

    await session.refresh(old_row)
    await session.refresh(recent_row)
    assert old_row.photo_object_key is None
    assert old_row.had_photo is True
    assert recent_row.photo_object_key is not None
    assert not old_path.exists()
    assert new_path.is_file()


@pytest.mark.asyncio
async def test_reap_preserves_had_photo_for_achievements(ctx) -> None:
    from qr_chores.models.rewards import Achievement, CriteriaType
    from qr_chores.services.achievements import progress_for

    session, child, settings, _tmp = ctx
    chore = await _chore(session, child)
    old = TODAY - timedelta(days=120)
    await _completion_with_photo(
        session, chore=chore, child=child, settings=settings, local_date=old
    )
    ach = Achievement(
        title="Photo pro",
        description="",
        icon_key="camera",
        criteria_type=CriteriaType.photo_completions,
        criteria_json='{"count": 1}',
        points_reward=5,
        is_active=True,
    )
    session.add(ach)
    await session.commit()

    with frozen_at(TODAY, tz=TZ):
        await reap_old_photos(session, settings, retention_days=90)
        progress = await progress_for(session, child.id, ach, settings)
    assert progress == 1


@pytest.mark.asyncio
async def test_reap_override_retention_days(ctx) -> None:
    session, child, settings, _tmp = ctx
    chore = await _chore(session, child)
    mid = TODAY - timedelta(days=40)
    await _completion_with_photo(
        session, chore=chore, child=child, settings=settings, local_date=mid
    )
    settings.photo_retention_days = 90
    with frozen_at(TODAY, tz=TZ):
        # Default 90: mid is not old enough
        r1 = await reap_old_photos(session, settings, dry_run=True)
        assert r1.candidates == 0
        # Override 30: mid is reaped
        r2 = await reap_old_photos(session, settings, retention_days=30, dry_run=True)
        assert r2.candidates == 1


@pytest.mark.asyncio
async def test_reap_storage_error_other_keeps_key(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    session, child, settings, _tmp = ctx
    chore = await _chore(session, child)
    old = TODAY - timedelta(days=100)
    row = await _completion_with_photo(
        session, chore=chore, child=child, settings=settings, local_date=old
    )

    from qr_chores.services import photo_reap as photo_reap_mod
    from qr_chores.services.storage import StorageError

    class BoomStorage:
        def delete(self, key: str) -> None:
            raise StorageError("permission denied", "forbidden")

    monkeypatch.setattr(photo_reap_mod, "get_photo_storage", lambda _s: BoomStorage())

    with frozen_at(TODAY, tz=TZ):
        result = await reap_old_photos(session, settings)

    assert result.failed == 1
    assert result.cleared_keys == 0
    await session.refresh(row)
    assert row.photo_object_key is not None


@pytest.mark.asyncio
async def test_reap_missing_file_still_clears_key(ctx) -> None:
    session, child, settings, _tmp = ctx
    chore = await _chore(session, child)
    old = TODAY - timedelta(days=100)
    row = ChoreCompletion(
        chore_id=chore.id,
        user_id=child.id,
        local_date=old,
        completed_at=datetime(old.year, old.month, old.day, 12, 0, tzinfo=TZ),
        timing=TimingStatus.on_time,
        photo_object_key="completions/ghost/missing.png",
        had_photo=True,
        points_awarded=1,
    )
    session.add(row)
    await session.commit()

    with frozen_at(TODAY, tz=TZ):
        result = await reap_old_photos(session, settings)

    assert result.cleared_keys == 1
    await session.refresh(row)
    assert row.photo_object_key is None
    # Local delete is a no-op when missing; still counts as deleted path.
    assert result.deleted == 1
