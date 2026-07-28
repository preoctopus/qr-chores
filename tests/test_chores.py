"""Parent chore CRUD and QR routes."""

from datetime import UTC, date, datetime, time

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from conftest import create_user
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy, TimingStatus
from qr_chores.models.user import User, UserRole
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
async def test_parent_creates_chore(
    client: AsyncClient, parent_user: User, app, child_user: User
) -> None:
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
            "assignee_user_id": str(child_user.id),
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
    client: AsyncClient, parent_user: User, app, child_user: User
) -> None:
    await _login_parent(client, parent_user)
    chore = await _create_chore(
        app.state.session_factory, title="Make bed", assignee_user_id=child_user.id
    )

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
    client: AsyncClient, parent_user: User, app, child_user: User
) -> None:
    await _login_parent(client, parent_user)
    chore = await _create_chore(
        app.state.session_factory, title="Old name", assignee_user_id=child_user.id
    )

    edit = await client.post(
        f"/chores/{chore.id}/edit",
        data={
            "title": "New name",
            "description": "",
            "due_time": "09:00",
            "base_points": "5",
            "photo_policy": "required",
            "schedule_day": ["0", "1", "2", "3", "4"],
            "assignee_user_id": str(child_user.id),
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


@pytest.mark.asyncio
async def test_parent_deletes_chore_without_history(
    client: AsyncClient, parent_user: User, app, child_user: User
) -> None:
    await _login_parent(client, parent_user)
    chore = await _create_chore(
        app.state.session_factory, title="Temp chore", assignee_user_id=child_user.id
    )
    chore_id = chore.id

    confirm = await client.get(f"/chores/{chore_id}/delete")
    assert confirm.status_code == 200
    assert "Delete chore" in confirm.text
    assert "Temp chore" in confirm.text
    assert "No completion history" in confirm.text

    deleted = await client.post(f"/chores/{chore_id}/delete", follow_redirects=False)
    assert deleted.status_code == 303
    assert deleted.headers["location"] == "/chores"

    async with app.state.session_factory() as session:
        assert await session.get(Chore, chore_id) is None

    listing = await client.get("/chores")
    assert "Temp chore" not in listing.text


@pytest.mark.asyncio
async def test_parent_deletes_chore_with_completions(
    client: AsyncClient, parent_user: User, child_user: User, app
) -> None:
    await _login_parent(client, parent_user)
    chore = await _create_chore(
        app.state.session_factory, title="Done once", assignee_user_id=child_user.id
    )
    chore_id = chore.id

    async with app.state.session_factory() as session:
        session.add(
            ChoreCompletion(
                chore_id=chore_id,
                user_id=child_user.id,
                local_date=date(2026, 7, 25),
                completed_at=datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
                timing=TimingStatus.on_time,
                points_awarded=10,
            )
        )
        await session.commit()

    confirm = await client.get(f"/chores/{chore_id}/delete")
    assert confirm.status_code == 200
    assert "1" in confirm.text
    assert "completion" in confirm.text.lower()

    deleted = await client.post(f"/chores/{chore_id}/delete", follow_redirects=False)
    assert deleted.status_code == 303

    async with app.state.session_factory() as session:
        assert await session.get(Chore, chore_id) is None
        remaining = (
            (
                await session.execute(
                    select(ChoreCompletion).where(ChoreCompletion.chore_id == chore_id)
                )
            )
            .scalars()
            .all()
        )
        assert remaining == []


@pytest.mark.asyncio
async def test_child_cannot_delete_chore(client: AsyncClient, child_user: User, app) -> None:
    chore = await _create_chore(app.state.session_factory, assignee_user_id=child_user.id)
    await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
    )
    assert (await client.get(f"/chores/{chore.id}/delete")).status_code == 403
    assert (await client.post(f"/chores/{chore.id}/delete")).status_code == 403


@pytest.mark.asyncio
async def test_parent_activate_and_edit_form(
    client: AsyncClient, parent_user: User, app, child_user: User
) -> None:
    await _login_parent(client, parent_user)
    chore = await _create_chore(
        app.state.session_factory, title="Inactive", is_active=False, assignee_user_id=child_user.id
    )

    form = await client.get(f"/chores/{chore.id}/edit")
    assert form.status_code == 200
    assert "Inactive" in form.text

    act = await client.post(f"/chores/{chore.id}/activate", follow_redirects=False)
    assert act.status_code == 303
    async with app.state.session_factory() as session:
        row = await session.get(Chore, chore.id)
        assert row is not None
        assert row.is_active is True

    bad = await client.post(
        f"/chores/{chore.id}/edit",
        data={
            "title": "   ",
            "description": "",
            "due_time": "10:00",
            "base_points": "1",
            "photo_policy": "none",
            "schedule_day": ["0"],
        },
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_other_parents_chore_is_invisible(
    client: AsyncClient, parent_user: User, app, child_user: User
) -> None:
    """A chore assigned to another parent's child is treated as not found."""
    other_parent = await create_user(
        app.state.session_factory,
        email="other-parent@example.com",
        first_name="Other",
        last_name="Parent",
        password="parent-pass",
        role=UserRole.parent,
    )
    other_child = await create_user(
        app.state.session_factory,
        email="other-kid@example.com",
        first_name="Other",
        last_name="Kid",
        password="child-pass",
        role=UserRole.child,
        parent_id=other_parent.id,
    )
    chore = await _create_chore(
        app.state.session_factory, title="Not yours", assignee_user_id=other_child.id
    )

    await _login_parent(client, parent_user)

    edit_form = await client.get(f"/chores/{chore.id}/edit", follow_redirects=False)
    assert edit_form.status_code == 303
    assert edit_form.headers["location"] == "/chores"

    edit_post = await client.post(
        f"/chores/{chore.id}/edit",
        data={
            "title": "Hijacked",
            "description": "",
            "due_time": "10:00",
            "base_points": "1",
            "photo_policy": "none",
            "schedule_day": ["0"],
            "assignee_user_id": str(child_user.id),
        },
        follow_redirects=False,
    )
    assert edit_post.status_code == 303
    assert edit_post.headers["location"] == "/chores"

    async with app.state.session_factory() as session:
        untouched = await session.get(Chore, chore.id)
        assert untouched is not None
        assert untouched.title == "Not yours"


@pytest.mark.asyncio
async def test_parent_creates_chore_with_invalid_base_points_and_assignee(
    client: AsyncClient, parent_user: User, app, child_user: User
) -> None:
    await _login_parent(client, parent_user)

    bad_points = await client.post(
        "/chores",
        data={
            "title": "Sweep porch",
            "description": "",
            "due_time": "10:00",
            "base_points": "not-a-number",
            "photo_policy": "none",
            "schedule_day": ["0"],
            "assignee_user_id": str(child_user.id),
        },
        follow_redirects=False,
    )
    assert bad_points.status_code == 303
    async with app.state.session_factory() as session:
        chore = (
            await session.execute(select(Chore).where(Chore.title == "Sweep porch"))
        ).scalar_one()
        assert chore.base_points == 10

    bad_assignee = await client.post(
        "/chores",
        data={
            "title": "Orphan chore",
            "description": "",
            "due_time": "10:00",
            "base_points": "5",
            "photo_policy": "none",
            "schedule_day": ["0"],
            "assignee_user_id": "999999",
        },
    )
    assert bad_assignee.status_code == 400
    assert "active children" in bad_assignee.text.lower()


@pytest.mark.asyncio
async def test_parent_edits_chore_with_invalid_assignee(
    client: AsyncClient, parent_user: User, app, child_user: User
) -> None:
    await _login_parent(client, parent_user)
    chore = await _create_chore(
        app.state.session_factory, title="Fold laundry", assignee_user_id=child_user.id
    )

    response = await client.post(
        f"/chores/{chore.id}/edit",
        data={
            "title": "Fold laundry",
            "description": "",
            "due_time": "10:00",
            "base_points": "5",
            "photo_policy": "none",
            "schedule_day": ["0"],
            "assignee_user_id": "999999",
        },
    )
    assert response.status_code == 400
    assert "active children" in response.text.lower()
