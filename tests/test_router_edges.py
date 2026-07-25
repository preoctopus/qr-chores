"""High-ROI edge-path coverage for chores, rewards, complete, and photos."""

from datetime import time
from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy
from qr_chores.models.rewards import Achievement
from qr_chores.models.user import User
from qr_chores.services.qr import new_qr_token

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _login_parent(client: AsyncClient, parent_user: User) -> None:
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )


async def _login_child(client: AsyncClient, child_user: User) -> None:
    await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
    )


async def _create_chore(session_factory, **kwargs) -> Chore:
    defaults = {
        "title": "Edge chore",
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


# --- Chores ---


@pytest.mark.asyncio
async def test_chores_new_form(client: AsyncClient, parent_user: User) -> None:
    await _login_parent(client, parent_user)
    response = await client.get("/chores/new")
    assert response.status_code == 200
    assert "New chore" in response.text or "title" in response.text.lower()


@pytest.mark.asyncio
async def test_chores_create_empty_title(client: AsyncClient, parent_user: User) -> None:
    await _login_parent(client, parent_user)
    response = await client.post(
        "/chores",
        data={
            "title": "   ",
            "description": "",
            "due_time": "20:00",
            "base_points": "10",
            "photo_policy": "none",
            "schedule_day": ["0"],
        },
    )
    assert response.status_code == 400
    assert "Title is required" in response.text


@pytest.mark.asyncio
async def test_chores_create_invalid_due_time(client: AsyncClient, parent_user: User) -> None:
    await _login_parent(client, parent_user)
    response = await client.post(
        "/chores",
        data={
            "title": "Bad due",
            "description": "",
            "due_time": "not-a-time",
            "base_points": "10",
            "photo_policy": "none",
            "schedule_day": ["0"],
        },
    )
    assert response.status_code == 400
    assert "Invalid" in response.text


@pytest.mark.asyncio
async def test_chores_missing_ids_redirect(client: AsyncClient, parent_user: User) -> None:
    await _login_parent(client, parent_user)
    missing = 999_999
    for path in (
        f"/chores/{missing}/edit",
        f"/chores/{missing}/delete",
        f"/chores/{missing}/qr",
    ):
        resp = await client.get(path, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/chores"

    png = await client.get(f"/chores/{missing}/qr.png")
    assert png.status_code == 404

    for path in (
        f"/chores/{missing}/activate",
        f"/chores/{missing}/deactivate",
        f"/chores/{missing}/delete",
    ):
        resp = await client.post(path, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/chores"


@pytest.mark.asyncio
async def test_chores_edit_invalid_policy(client: AsyncClient, parent_user: User, app) -> None:
    await _login_parent(client, parent_user)
    chore = await _create_chore(app.state.session_factory, title="Keep me")
    response = await client.post(
        f"/chores/{chore.id}/edit",
        data={
            "title": "Keep me",
            "description": "",
            "due_time": "10:00",
            "base_points": "not-int-ok",  # falls back to 10
            "photo_policy": "not-a-policy",
            "schedule_day": ["0"],
        },
    )
    assert response.status_code == 400


# --- Rewards ---


@pytest.mark.asyncio
async def test_rewards_achievement_new_and_edit_toggle(
    client: AsyncClient, parent_user: User, app
) -> None:
    await _login_parent(client, parent_user)

    new_form = await client.get("/rewards/achievements/new")
    assert new_form.status_code == 200

    bad = await client.post(
        "/rewards/achievements",
        data={
            "title": "",
            "description": "x",
            "icon_key": "star",
            "criteria_type": "total_completions",
            "threshold": "2",
            "points_reward": "5",
        },
    )
    assert bad.status_code == 400
    assert "Title is required" in bad.text

    invalid = await client.post(
        "/rewards/achievements",
        data={
            "title": "Nope",
            "description": "",
            "icon_key": "star",
            "criteria_type": "not_a_type",
            "threshold": "2",
            "points_reward": "5",
        },
    )
    assert invalid.status_code == 400

    create = await client.post(
        "/rewards/achievements",
        data={
            "title": "Edge Badge",
            "description": "Do stuff",
            "icon_key": "star",
            "criteria_type": "streak_days",
            "threshold": "4",
            "points_reward": "12",
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    async with app.state.session_factory() as session:
        ach = (
            await session.execute(select(Achievement).where(Achievement.title == "Edge Badge"))
        ).scalar_one()
        ach_id = ach.id
        assert '"days": 4' in ach.criteria_json or '"days":4' in ach.criteria_json.replace(" ", "")

    edit_form = await client.get(f"/rewards/achievements/{ach_id}/edit")
    assert edit_form.status_code == 200
    assert "Edge Badge" in edit_form.text

    edited = await client.post(
        f"/rewards/achievements/{ach_id}/edit",
        data={
            "title": "Edge Badge 2",
            "description": "Updated",
            "icon_key": "fire",
            "criteria_type": "total_completions",
            "threshold": "3",
            "points_reward": "20",
        },
        follow_redirects=False,
    )
    assert edited.status_code == 303

    toggled = await client.post(
        f"/rewards/achievements/{ach_id}/toggle",
        follow_redirects=False,
    )
    assert toggled.status_code == 303
    async with app.state.session_factory() as session:
        row = await session.get(Achievement, ach_id)
        assert row is not None
        assert row.is_active is False
        assert row.title == "Edge Badge 2"

    # Missing achievement id
    assert (
        await client.get("/rewards/achievements/999999/edit", follow_redirects=False)
    ).status_code == 303
    assert (
        await client.post(
            "/rewards/achievements/999999/edit",
            data={
                "title": "x",
                "description": "",
                "icon_key": "star",
                "criteria_type": "total_completions",
                "threshold": "1",
                "points_reward": "0",
            },
            follow_redirects=False,
        )
    ).status_code == 303
    assert (
        await client.post("/rewards/achievements/999999/toggle", follow_redirects=False)
    ).status_code == 303


# --- Complete ---


@pytest.mark.asyncio
async def test_complete_unknown_token(client: AsyncClient, child_user: User) -> None:
    await _login_child(client, child_user)
    get_resp = await client.get("/c/not-a-real-token")
    assert get_resp.status_code == 404
    post_resp = await client.post("/c/not-a-real-token")
    assert post_resp.status_code == 404


@pytest.mark.asyncio
async def test_complete_not_scheduled_http(client: AsyncClient, child_user: User, app) -> None:
    chore = await _create_chore(
        app.state.session_factory,
        schedule_days="",  # never scheduled
        title="Off day only",
    )
    await _login_child(client, child_user)
    response = await client.post(f"/c/{chore.qr_token}")
    assert response.status_code == 400
    assert "not scheduled" in response.text.lower() or "Can’t complete" in response.text


@pytest.mark.asyncio
async def test_complete_already_done_confirm_page(
    client: AsyncClient, child_user: User, app
) -> None:
    chore = await _create_chore(app.state.session_factory, title="Once only")
    await _login_child(client, child_user)
    assert (await client.post(f"/c/{chore.qr_token}")).status_code == 200
    again = await client.get(f"/c/{chore.qr_token}")
    assert again.status_code == 200
    # Confirm page shows existing completion rather than the complete CTA only
    assert "Once only" in again.text


@pytest.mark.asyncio
async def test_complete_rejects_oversized_photo(
    client: AsyncClient, child_user: User, app, monkeypatch: pytest.MonkeyPatch
) -> None:
    from qr_chores.config import get_settings

    chore = await _create_chore(
        app.state.session_factory,
        photo_policy=PhotoPolicy.required,
    )
    # Tiny limit so we don't allocate multi-MB fixtures
    monkeypatch.setenv("PHOTO_MAX_BYTES", "50")
    get_settings.cache_clear()
    await _login_child(client, child_user)
    # PNG header + padding over 50 bytes
    blob = TINY_PNG + b"x" * 100
    response = await client.post(
        f"/c/{chore.qr_token}",
        files={"photo": ("big.png", BytesIO(blob), "image/png")},
    )
    assert response.status_code == 400
    assert "too large" in response.text.lower()
    get_settings.cache_clear()


# --- Photos ---


@pytest.mark.asyncio
async def test_photo_missing_completion(client: AsyncClient, parent_user: User) -> None:
    await _login_parent(client, parent_user)
    response = await client.get("/photos/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_photo_completion_without_key(
    client: AsyncClient, parent_user: User, child_user: User, app
) -> None:
    chore = await _create_chore(app.state.session_factory)
    await _login_child(client, child_user)
    await client.post(f"/c/{chore.qr_token}")

    async with app.state.session_factory() as session:
        completion = (await session.execute(select(ChoreCompletion))).scalar_one()
        cid = completion.id
        assert completion.photo_object_key is None

    await _login_parent(client, parent_user)
    response = await client.get(f"/photos/{cid}")
    assert response.status_code == 404
