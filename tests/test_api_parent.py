"""Internal /api/v1 parent endpoint tests (phases 2–3)."""

from datetime import UTC, date, datetime, time

import pytest
from httpx import AsyncClient

from qr_chores.config import get_settings
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy, TimingStatus
from qr_chores.models.user import User
from qr_chores.services.qr import new_qr_token
from qr_chores.services.storage import get_photo_storage

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def api_login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_chore(session_factory, **kwargs) -> Chore:
    defaults = {
        "title": "Parent API chore",
        "description": "desc",
        "qr_token": new_qr_token(),
        "due_time": time(20, 0),
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


@pytest.mark.asyncio
async def test_today_parent(client: AsyncClient, parent_user: User, child_user: User, app) -> None:
    await _create_chore(app.state.session_factory, assignee_user_id=child_user.id)
    token = await api_login(client, parent_user.email, "parent-pass")
    response = await client.get("/api/v1/today", headers=auth_header(token))
    assert response.status_code == 200
    data = response.json()
    assert "local_date" in data
    assert "board" in data
    assert len(data["board"]) >= 1
    assert data["board"][0]["chore"]["title"] == "Parent API chore"


@pytest.mark.asyncio
async def test_today_child_forbidden(client: AsyncClient, child_user: User) -> None:
    token = await api_login(client, child_user.email, "child-pass")
    response = await client.get("/api/v1/today", headers=auth_header(token))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_chores_crud(client: AsyncClient, parent_user: User, child_user: User, app) -> None:
    token = await api_login(client, parent_user.email, "parent-pass")
    headers = auth_header(token)

    created = await client.post(
        "/api/v1/chores",
        headers=headers,
        json={
            "title": "Trash night",
            "description": "Bins out",
            "due_time": "19:30:00",
            "schedule_days": "01234",
            "photo_policy": "optional",
            "base_points": 20,
            "assignee_user_id": child_user.id,
        },
    )
    assert created.status_code == 201, created.text
    chore = created.json()
    assert chore["title"] == "Trash night"
    assert chore["qr_token"]
    assert chore["is_active"] is True
    assert chore["schedule_days"] == "01234"
    chore_id = chore["id"]

    listed = await client.get("/api/v1/chores", headers=headers)
    assert listed.status_code == 200
    assert any(c["id"] == chore_id for c in listed.json()["chores"])

    got = await client.get(f"/api/v1/chores/{chore_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["title"] == "Trash night"

    patched = await client.patch(
        f"/api/v1/chores/{chore_id}",
        headers=headers,
        json={"title": "Trash morning", "base_points": 25},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Trash morning"
    assert patched.json()["base_points"] == 25

    deactivated = await client.post(
        f"/api/v1/chores/{chore_id}/deactivate",
        headers=headers,
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    activated = await client.post(
        f"/api/v1/chores/{chore_id}/activate",
        headers=headers,
    )
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True

    qr = await client.get(f"/api/v1/chores/{chore_id}/qr", headers=headers)
    assert qr.status_code == 200
    qr_body = qr.json()
    assert qr_body["qr_token"] == chore["qr_token"]
    assert "/c/" in qr_body["qr_url"]
    assert qr_body["png_path"] == f"/api/v1/chores/{chore_id}/qr.png"

    png = await client.get(f"/api/v1/chores/{chore_id}/qr.png", headers=headers)
    assert png.status_code == 200
    assert png.headers["content-type"].startswith("image/png")
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"

    deleted = await client.delete(f"/api/v1/chores/{chore_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    missing = await client.get(f"/api/v1/chores/{chore_id}", headers=headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_child_cannot_write_chores(client: AsyncClient, child_user: User) -> None:
    token = await api_login(client, child_user.email, "child-pass")
    response = await client.post(
        "/api/v1/chores",
        headers=auth_header(token),
        json={
            "title": "Nope",
            "due_time": "10:00:00",
            "photo_policy": "none",
            "base_points": 1,
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_chore_validation(
    client: AsyncClient, parent_user: User, child_user: User
) -> None:
    token = await api_login(client, parent_user.email, "parent-pass")
    response = await client.post(
        "/api/v1/chores",
        headers=auth_header(token),
        json={
            "title": "   ",
            "due_time": "10:00:00",
            "photo_policy": "none",
            "assignee_user_id": child_user.id,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_history_and_photo(
    client: AsyncClient, parent_user: User, child_user: User, app
) -> None:
    chore = await _create_chore(app.state.session_factory, assignee_user_id=child_user.id)
    settings_obj = get_settings()
    key = f"completions/{chore.id}/2026-07-26/test.png"
    get_photo_storage(settings_obj).save(key, TINY_PNG, "image/png")

    async with app.state.session_factory() as session:
        completion = ChoreCompletion(
            chore_id=chore.id,
            user_id=child_user.id,
            local_date=date(2026, 7, 26),
            completed_at=datetime(2026, 7, 26, 18, 0, tzinfo=UTC),
            timing=TimingStatus.on_time,
            photo_object_key=key,
            points_awarded=12,
        )
        session.add(completion)
        await session.commit()
        await session.refresh(completion)
        completion_id = completion.id

    token = await api_login(client, parent_user.email, "parent-pass")
    headers = auth_header(token)

    history = await client.get("/api/v1/history", headers=headers)
    assert history.status_code == 200
    body = history.json()
    assert body["limit"] == 50
    assert any(item["chore_id"] == chore.id for item in body["items"])
    item = next(i for i in body["items"] if i["chore_id"] == chore.id)
    assert item["chore_title"] == chore.title
    assert item["completion"]["has_photo"] is True

    photo = await client.get(f"/api/v1/photos/{completion_id}", headers=headers)
    assert photo.status_code == 200
    assert photo.content == TINY_PNG

    child_token = await api_login(client, child_user.email, "child-pass")
    child_photo = await client.get(
        f"/api/v1/photos/{completion_id}",
        headers=auth_header(child_token),
    )
    assert child_photo.status_code == 200


@pytest.mark.asyncio
async def test_rewards_admin(client: AsyncClient, parent_user: User) -> None:
    token = await api_login(client, parent_user.email, "parent-pass")
    headers = auth_header(token)

    rewards = await client.get("/api/v1/rewards", headers=headers)
    assert rewards.status_code == 200
    data = rewards.json()
    assert "bonuses" in data
    assert "achievements" in data
    assert "early_bonus_points" in data["bonuses"]

    bonuses = await client.put(
        "/api/v1/rewards/bonuses",
        headers=headers,
        json={
            "early_bonus_points": 7,
            "on_time_bonus_points": 3,
            "late_bonus_points": 1,
        },
    )
    assert bonuses.status_code == 200
    assert bonuses.json()["early_bonus_points"] == 7

    created = await client.post(
        "/api/v1/rewards/achievements",
        headers=headers,
        json={
            "title": "Photo pro",
            "description": "Snap it",
            "icon_key": "camera",
            "criteria_type": "photo_completions",
            "threshold": 3,
            "points_reward": 15,
        },
    )
    assert created.status_code == 201, created.text
    ach = created.json()
    assert ach["title"] == "Photo pro"
    assert ach["threshold"] == 3
    assert ach["is_active"] is True
    ach_id = ach["id"]

    patched = await client.patch(
        f"/api/v1/rewards/achievements/{ach_id}",
        headers=headers,
        json={
            "title": "Photo pro+",
            "description": "Snap it well",
            "icon_key": "  camera  ",
            "criteria_type": "photo_completions",
            "threshold": 5,
            "points_reward": 20,
        },
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["threshold"] == 5
    assert body["points_reward"] == 20
    assert body["title"] == "Photo pro+"
    assert body["icon_key"] == "camera"

    toggled = await client.post(
        f"/api/v1/rewards/achievements/{ach_id}/toggle",
        headers=headers,
    )
    assert toggled.status_code == 200
    assert toggled.json()["is_active"] is False


@pytest.mark.asyncio
async def test_child_cannot_manage_rewards(client: AsyncClient, child_user: User) -> None:
    token = await api_login(client, child_user.email, "child-pass")
    response = await client.get("/api/v1/rewards", headers=auth_header(token))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_parent_routes(client: AsyncClient) -> None:
    for path, method in (
        ("/api/v1/today", "get"),
        ("/api/v1/history", "get"),
        ("/api/v1/chores", "get"),
        ("/api/v1/rewards", "get"),
        ("/api/v1/photos/1", "get"),
    ):
        response = await getattr(client, method)(path)
        assert response.status_code == 401, path
        assert response.headers.get("content-type", "").startswith("application/json")
