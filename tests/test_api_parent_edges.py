"""Additional /api/v1 parent edge-case HTTP tests (404s, filters, roles)."""

from datetime import time

import pytest
from httpx import AsyncClient

from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.models.user import User
from qr_chores.services.qr import new_qr_token


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


@pytest.mark.asyncio
async def test_chore_404s(client: AsyncClient, parent_user: User) -> None:
    token = await api_login(client, parent_user.email, "parent-pass")
    headers = auth_header(token)
    missing_id = 999_999

    assert (await client.get(f"/api/v1/chores/{missing_id}", headers=headers)).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/chores/{missing_id}",
            headers=headers,
            json={"title": "Nope"},
        )
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/chores/{missing_id}/deactivate", headers=headers)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/chores/{missing_id}/activate", headers=headers)
    ).status_code == 404
    assert (await client.delete(f"/api/v1/chores/{missing_id}", headers=headers)).status_code == 404
    assert (await client.get(f"/api/v1/chores/{missing_id}/qr", headers=headers)).status_code == 404
    assert (
        await client.get(f"/api/v1/chores/{missing_id}/qr.png", headers=headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_include_inactive_filter(client: AsyncClient, parent_user: User, app) -> None:
    active = await _create_chore(app.state.session_factory, title="Active one")
    inactive = await _create_chore(app.state.session_factory, title="Inactive one", is_active=False)
    token = await api_login(client, parent_user.email, "parent-pass")
    headers = auth_header(token)

    all_chores = await client.get("/api/v1/chores", headers=headers)
    ids = {c["id"] for c in all_chores.json()["chores"]}
    assert active.id in ids
    assert inactive.id in ids

    only_active = await client.get(
        "/api/v1/chores",
        headers=headers,
        params={"include_inactive": "false"},
    )
    ids_active = {c["id"] for c in only_active.json()["chores"]}
    assert active.id in ids_active
    assert inactive.id not in ids_active


@pytest.mark.asyncio
async def test_clear_description_patch(client: AsyncClient, parent_user: User, app) -> None:
    chore = await _create_chore(
        app.state.session_factory, title="Has desc", description="remove me"
    )
    token = await api_login(client, parent_user.email, "parent-pass")
    headers = auth_header(token)

    patched = await client.patch(
        f"/api/v1/chores/{chore.id}",
        headers=headers,
        json={"clear_description": True},
    )
    assert patched.status_code == 200
    assert patched.json()["description"] is None


@pytest.mark.asyncio
async def test_child_forbidden_on_parent_writes(client: AsyncClient, child_user: User, app) -> None:
    chore = await _create_chore(app.state.session_factory)
    token = await api_login(client, child_user.email, "child-pass")
    headers = auth_header(token)

    assert (await client.get("/api/v1/chores", headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/chores/{chore.id}", headers=headers)).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/chores/{chore.id}",
            headers=headers,
            json={"title": "Hack"},
        )
    ).status_code == 403
    assert (
        await client.post(f"/api/v1/chores/{chore.id}/deactivate", headers=headers)
    ).status_code == 403
    assert (await client.delete(f"/api/v1/chores/{chore.id}", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/history", headers=headers)).status_code == 403
    assert (
        await client.put(
            "/api/v1/rewards/bonuses",
            headers=headers,
            json={
                "early_bonus_points": 1,
                "on_time_bonus_points": 1,
                "late_bonus_points": 0,
            },
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_achievement_404s(client: AsyncClient, parent_user: User) -> None:
    token = await api_login(client, parent_user.email, "parent-pass")
    headers = auth_header(token)
    missing = 999_999

    assert (
        await client.patch(
            f"/api/v1/rewards/achievements/{missing}",
            headers=headers,
            json={"title": "Nope"},
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/rewards/achievements/{missing}/toggle",
            headers=headers,
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_photo_not_found(client: AsyncClient, parent_user: User) -> None:
    token = await api_login(client, parent_user.email, "parent-pass")
    response = await client.get("/api/v1/photos/999999", headers=auth_header(token))
    assert response.status_code == 404
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_history_limit(client: AsyncClient, parent_user: User) -> None:
    token = await api_login(client, parent_user.email, "parent-pass")
    headers = auth_header(token)

    ok = await client.get("/api/v1/history", headers=headers, params={"limit": 10})
    assert ok.status_code == 200
    assert ok.json()["limit"] == 10

    bad = await client.get("/api/v1/history", headers=headers, params={"limit": 0})
    assert bad.status_code == 422

    bad_high = await client.get("/api/v1/history", headers=headers, params={"limit": 500})
    assert bad_high.status_code == 422


@pytest.mark.asyncio
async def test_create_invalid_photo_policy_http(client: AsyncClient, parent_user: User) -> None:
    token = await api_login(client, parent_user.email, "parent-pass")
    response = await client.post(
        "/api/v1/chores",
        headers=auth_header(token),
        json={
            "title": "X",
            "due_time": "10:00:00",
            "photo_policy": "maybe",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_all_fields(client: AsyncClient, parent_user: User, app) -> None:
    chore = await _create_chore(app.state.session_factory)
    token = await api_login(client, parent_user.email, "parent-pass")
    headers = auth_header(token)

    patched = await client.patch(
        f"/api/v1/chores/{chore.id}",
        headers=headers,
        json={
            "title": "Updated",
            "description": " new desc ",
            "due_time": "18:15:00",
            "schedule_days": "01234",
            "photo_policy": "required",
            "base_points": 99,
        },
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["title"] == "Updated"
    assert body["description"] == "new desc"
    assert body["due_time"].startswith("18:15")
    assert body["schedule_days"] == "01234"
    assert body["photo_policy"] == "required"
    assert body["base_points"] == 99
