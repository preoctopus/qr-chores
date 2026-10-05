"""Unit tests for undo completion feature (Issue #19)."""

from datetime import time

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from qr_chores.auth.passwords import hash_password
from qr_chores.config import Settings, get_settings
from qr_chores.db import Base
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy
from qr_chores.models.rewards import PointLedger
from qr_chores.models.user import User, UserRole
from qr_chores.services.completion import (
    CompletionError,
    complete_chore,
    undo_completion,
)
from qr_chores.services.points import points_balance
from qr_chores.services.qr import new_qr_token


@pytest.fixture
async def undo_ctx(tmp_path):
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
    )
    async with factory() as session:
        parent = User(
            email="parent@example.com",
            display_name="Parent",
            password_hash=hash_password("x"),
            role=UserRole.parent,
            is_active=True,
        )
        session.add(parent)
        await session.flush()

        child = User(
            email="child@example.com",
            display_name="Child",
            password_hash=hash_password("x"),
            role=UserRole.child,
            parent_id=parent.id,
            is_active=True,
        )
        session.add(child)
        await session.commit()
        await session.refresh(parent)
        await session.refresh(child)

        yield session, parent, child, settings
    await engine.dispose()


@pytest.mark.asyncio
async def test_undo_completion_success(undo_ctx):
    session, parent, child, settings = undo_ctx

    chore = Chore(
        title="Clean room",
        qr_token=new_qr_token(),
        due_time=time(23, 59),
        schedule_days="0123456",
        photo_policy=PhotoPolicy.none,
        base_points=10,
        assignee_user_id=child.id,
        is_active=True,
    )
    session.add(chore)
    await session.commit()
    await session.refresh(chore)

    res = await complete_chore(session, chore=chore, user=child, settings=settings)
    comp_id = res.completion.id

    bal_before = await points_balance(session, child.id)
    assert bal_before > 0

    undo_res = await undo_completion(
        session,
        completion_id=comp_id,
        parent_id=parent.id,
        settings=settings,
    )

    assert undo_res.completion_id == comp_id
    assert undo_res.chore_id == chore.id

    # Balance is restored to zero
    bal_after = await points_balance(session, child.id)
    assert bal_after == 0

    # Completion row is deleted
    db_comp = await session.get(ChoreCompletion, comp_id)
    assert db_comp is None

    # Negative compensating entries exist in PointLedger
    ledger_rows = (
        await session.scalars(
            select(PointLedger).where(
                PointLedger.user_id == child.id,
                PointLedger.ref_type == "completion_undo",
            )
        )
    ).all()
    assert len(ledger_rows) >= 1

    # Same chore can be completed again today
    retry_res = await complete_chore(session, chore=chore, user=child, settings=settings)
    assert retry_res.already_done is False


@pytest.mark.asyncio
async def test_undo_completion_unauthorized_other_parent(undo_ctx):
    session, parent, child, settings = undo_ctx

    other_parent = User(
        email="other@example.com",
        display_name="Other",
        password_hash=hash_password("x"),
        role=UserRole.parent,
        is_active=True,
    )
    session.add(other_parent)
    await session.commit()
    await session.refresh(other_parent)

    chore = Chore(
        title="Sweep",
        qr_token=new_qr_token(),
        due_time=time(23, 59),
        schedule_days="0123456",
        photo_policy=PhotoPolicy.none,
        base_points=10,
        assignee_user_id=child.id,
        is_active=True,
    )
    session.add(chore)
    await session.commit()
    await session.refresh(chore)

    res = await complete_chore(session, chore=chore, user=child, settings=settings)

    with pytest.raises(CompletionError) as exc_info:
        await undo_completion(
            session,
            completion_id=res.completion.id,
            parent_id=other_parent.id,
            settings=settings,
        )
    assert exc_info.value.code == "not_found"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_html_and_api_undo_completion(
    client,
    parent_user,
    child_user,
    app,
):
    async with app.state.session_factory() as session:
        chore = Chore(
            title="Wipe table",
            qr_token=new_qr_token(),
            due_time=time(23, 59),
            schedule_days="0123456",
            photo_policy=PhotoPolicy.none,
            base_points=10,
            assignee_user_id=child_user.id,
            is_active=True,
        )
        session.add(chore)
        await session.commit()
        await session.refresh(chore)

        res = await complete_chore(session, chore=chore, user=child_user, settings=get_settings())
        comp_id = res.completion.id

    # 1. API undo
    token_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": parent_user.email, "password": "parent-pass"},
    )
    token = token_resp.json()["access_token"]

    api_undo = await client.post(
        f"/api/v1/completions/{comp_id}/undo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert api_undo.status_code == 200
    assert api_undo.json()["success"] is True

    # 2. HTML undo
    async with app.state.session_factory() as session:
        res2 = await complete_chore(session, chore=chore, user=child_user, settings=get_settings())
        comp_id2 = res2.completion.id

    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
        follow_redirects=False,
    )

    html_undo = await client.post(
        f"/completions/{comp_id2}/undo",
        data={"next": "/today"},
        follow_redirects=False,
    )
    assert html_undo.status_code == 303
    assert html_undo.headers["location"] == "/today"
