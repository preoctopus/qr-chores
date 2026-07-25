"""Parent chore CRUD and QR routes."""

from datetime import time

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.models.user import User
from qr_chores.services.qr import new_qr_token


async def _login_parent(client: AsyncClient, parent_user: User) -> None:
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )


async def _create_chore(session_factory, **kwargs) -> Chore:
    defaults = {
        "title": "Unload dishwasher",
        "description": None,
        "qr_token": new_qr_token(),
        "due_time": time(20, 0),
        "schedule_days": "0123456",
        "photo_policy": PhotoPolicy.none,
        "base_points": 10,
        "is_active": True,
    }
    defaults.update(kwargs)
    async with session_factory() as session:
        chore = Chore(**defaults)
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        return chore


@pytest.mark.asyncio
async def test_child_cannot_list_chores(client: AsyncClient, child_user: User) -> None:
    await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
    )
    response = await client.get("/chores")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_parent_creates_chore(client: AsyncClient, parent_user: User, app) -> None:
    await _login_parent(client, parent_user)
    response = await client.post(
        "/chores",
        data={
            "title": "Take out trash",
            "description": "Bins to curb",
            "due_time": "19:30",
            "base_points": "15",
            "photo_policy": "optional",
            "schedule_day": ["0", "1", "2", "3", "4", "5", "6"],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/chores/")
    assert response.headers["location"].endswith("/qr")

    async with app.state.session_factory() as session:
        result = await session.execute(select(Chore).where(Chore.title == "Take out trash"))
        chore = result.scalar_one()
        assert chore.base_points == 15
        assert chore.photo_policy == PhotoPolicy.optional
        assert chore.qr_token
        assert chore.due_time.hour == 19
        assert chore.due_time.minute == 30


@pytest.mark.asyncio
async def test_parent_lists_and_views_qr(
    client: AsyncClient, parent_user: User, app
) -> None:
    await _login_parent(client, parent_user)
    chore = await _create_chore(app.state.session_factory, title="Make bed")

    listing = await client.get("/chores")
    assert listing.status_code == 200
    assert "Make bed" in listing.text

    qr_page = await client.get(f"/chores/{chore.id}/qr")
    assert qr_page.status_code == 200
    assert "Make bed" in qr_page.text
    assert f"/c/{chore.qr_token}" in qr_page.text

    png = await client.get(f"/chores/{chore.id}/qr.png")
    assert png.status_code == 200
    assert png.headers["content-type"].startswith("image/png")
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_parent_edits_and_deactivates(
    client: AsyncClient, parent_user: User, app
) -> None:
    await _login_parent(client, parent_user)
    chore = await _create_chore(app.state.session_factory, title="Old name")

    edit = await client.post(
        f"/chores/{chore.id}/edit",
        data={
            "title": "New name",
            "description": "",
            "due_time": "09:00",
            "base_points": "5",
            "photo_policy": "required",
            "schedule_day": ["0", "1", "2", "3", "4"],
        },
        follow_redirects=False,
    )
    assert edit.status_code == 303

    async with app.state.session_factory() as session:
        updated = await session.get(Chore, chore.id)
        assert updated is not None
        assert updated.title == "New name"
        assert updated.schedule_days == "01234"
        assert updated.photo_policy == PhotoPolicy.required

    deact = await client.post(f"/chores/{chore.id}/deactivate", follow_redirects=False)
    assert deact.status_code == 303
    async with app.state.session_factory() as session:
        updated = await session.get(Chore, chore.id)
        assert updated is not None
        assert updated.is_active is False
