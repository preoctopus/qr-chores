"""Child completion flow via QR token."""

from datetime import time

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy
from qr_chores.models.user import User
from qr_chores.services.qr import new_qr_token


async def _create_chore(session_factory, **kwargs) -> Chore:
    defaults = {
        "title": "Feed pets",
        "description": None,
        "qr_token": new_qr_token(),
        "due_time": time(21, 0),
        "schedule_days": "0123456",
        "photo_policy": PhotoPolicy.none,
        "base_points": 12,
        "is_active": True,
    }
    defaults.update(kwargs)
    async with session_factory() as session:
        chore = Chore(**defaults)
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        return chore


async def _login_child(client: AsyncClient, child_user: User) -> None:
    await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
    )


@pytest.mark.asyncio
async def test_qr_requires_login(client: AsyncClient, app) -> None:
    chore = await _create_chore(app.state.session_factory)
    response = await client.get(f"/c/{chore.qr_token}", follow_redirects=False)
    assert response.status_code == 303
    assert "/login" in response.headers["location"]
    assert chore.qr_token in response.headers["location"]


@pytest.mark.asyncio
async def test_parent_cannot_complete(client: AsyncClient, parent_user: User, app) -> None:
    chore = await _create_chore(app.state.session_factory)
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )
    get_resp = await client.get(f"/c/{chore.qr_token}")
    assert get_resp.status_code == 403
    post_resp = await client.post(f"/c/{chore.qr_token}")
    assert post_resp.status_code == 403


@pytest.mark.asyncio
async def test_child_completes_chore_once(client: AsyncClient, child_user: User, app) -> None:
    chore = await _create_chore(app.state.session_factory, title="Vacuum room")
    await _login_child(client, child_user)

    confirm = await client.get(f"/c/{chore.qr_token}")
    assert confirm.status_code == 200
    assert "Vacuum room" in confirm.text
    assert "I did it" in confirm.text
    # Issue #5: timing rules with this chore's due time (21:00)
    assert "Timing for a" in confirm.text
    assert "Early" in confirm.text
    assert "9:00 PM" in confirm.text  # due
    assert "8:00 PM" in confirm.text  # early cutoff (60 min before)

    done = await client.post(f"/c/{chore.qr_token}")
    assert done.status_code == 200
    assert "12" in done.text  # base points shown in breakdown
    assert "Timing for a" in done.text
    assert (
        "Early bonus" in done.text
        or "On-time bonus" in done.text
        or "Late bonus" in done.text
        or "Base" in done.text
    )

    async with app.state.session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(ChoreCompletion))
        assert count == 1
        completion = (await session.execute(select(ChoreCompletion))).scalar_one()
        assert completion.chore_id == chore.id
        assert completion.user_id == child_user.id
        # base 12 + optional timing bonus (defaults apply)
        assert completion.points_awarded >= 12

    # Second complete same day — no double award
    again = await client.post(f"/c/{chore.qr_token}")
    assert again.status_code == 200
    assert "Already" in again.text or "already" in again.text

    async with app.state.session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(ChoreCompletion))
        assert count == 1


@pytest.mark.asyncio
async def test_inactive_chore_not_completable(client: AsyncClient, child_user: User, app) -> None:
    chore = await _create_chore(app.state.session_factory, is_active=False)
    await _login_child(client, child_user)
    response = await client.get(f"/c/{chore.qr_token}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_child_home_shows_chore(client: AsyncClient, child_user: User, app) -> None:
    chore = await _create_chore(app.state.session_factory, title="Wipe counters")
    await _login_child(client, child_user)
    home = await client.get("/home")
    assert home.status_code == 200
    assert "Wipe counters" in home.text
    assert chore.qr_token in home.text


@pytest.mark.asyncio
async def test_parent_today_shows_status(
    client: AsyncClient, parent_user: User, child_user: User, app
) -> None:
    chore = await _create_chore(app.state.session_factory, title="Laundry")
    await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
    )
    await client.post(f"/c/{chore.qr_token}")

    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )
    today = await client.get("/today")
    assert today.status_code == 200
    assert "Laundry" in today.text
    assert "Done" in today.text
