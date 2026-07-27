"""Internal /api/v1 child endpoint tests."""

from datetime import time
from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy
from qr_chores.models.user import User
from qr_chores.services.qr import new_qr_token

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _create_chore(session_factory, **kwargs) -> Chore:
    defaults = {
        "title": "API dish duty",
        "description": None,
        "qr_token": new_qr_token(),
        "due_time": time(21, 0),
        "schedule_days": "0123456",
        "photo_policy": PhotoPolicy.none,
        "base_points": 15,
        "is_active": True,
    }
    defaults.update(kwargs)
    async with session_factory() as session:
        chore = Chore(**defaults)
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        return chore


async def api_login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_home_child(client: AsyncClient, child_user: User, app) -> None:
    await _create_chore(app.state.session_factory)
    token = await api_login(client, child_user.email, "child-pass")
    response = await client.get("/api/v1/home", headers=auth_header(token))
    assert response.status_code == 200
    data = response.json()
    assert "board" in data
    assert data["total_count"] >= 1
    assert "points_balance" in data


@pytest.mark.asyncio
async def test_home_parent_forbidden(client: AsyncClient, parent_user: User) -> None:
    token = await api_login(client, parent_user.email, "parent-pass")
    response = await client.get("/api/v1/home", headers=auth_header(token))
    assert response.status_code == 403
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_confirm_and_complete(client: AsyncClient, child_user: User, app) -> None:
    chore = await _create_chore(app.state.session_factory)
    token = await api_login(client, child_user.email, "child-pass")
    headers = auth_header(token)

    confirm = await client.get(f"/api/v1/c/{chore.qr_token}", headers=headers)
    assert confirm.status_code == 200
    body = confirm.json()
    assert body["chore"]["title"] == chore.title
    assert body["already_done"] is False
    assert body["scheduled_today"] is True

    complete = await client.post(
        f"/api/v1/c/{chore.qr_token}/complete",
        headers=headers,
    )
    assert complete.status_code == 200
    done = complete.json()
    assert done["already_done"] is False
    assert done["points"]["total"] >= chore.base_points
    assert done["completion"]["id"]

    async with app.state.session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(ChoreCompletion).where(ChoreCompletion.chore_id == chore.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1

    again = await client.post(
        f"/api/v1/c/{chore.qr_token}/complete",
        headers=headers,
    )
    assert again.status_code == 200
    assert again.json()["already_done"] is True


@pytest.mark.asyncio
async def test_parent_cannot_complete(client: AsyncClient, parent_user: User, app) -> None:
    chore = await _create_chore(app.state.session_factory)
    token = await api_login(client, parent_user.email, "parent-pass")
    response = await client.post(
        f"/api/v1/c/{chore.qr_token}/complete",
        headers=auth_header(token),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_complete_photo_required(client: AsyncClient, child_user: User, app) -> None:
    chore = await _create_chore(app.state.session_factory, photo_policy=PhotoPolicy.required)
    token = await api_login(client, child_user.email, "child-pass")
    headers = auth_header(token)

    missing = await client.post(
        f"/api/v1/c/{chore.qr_token}/complete",
        headers=headers,
    )
    assert missing.status_code == 400
    detail = missing.json()["detail"]
    assert detail["code"] == "photo_required" or "photo" in str(detail).lower()

    ok = await client.post(
        f"/api/v1/c/{chore.qr_token}/complete",
        headers=headers,
        files={"photo": ("proof.png", BytesIO(TINY_PNG), "image/png")},
    )
    assert ok.status_code == 200
    assert ok.json()["completion"]["has_photo"] is True


@pytest.mark.asyncio
async def test_achievements_child(client: AsyncClient, child_user: User) -> None:
    token = await api_login(client, child_user.email, "child-pass")
    response = await client.get(
        "/api/v1/achievements",
        headers=auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert "achievements" in data
    assert "unlocked_count" in data


@pytest.mark.asyncio
async def test_confirm_unknown_token(client: AsyncClient, child_user: User) -> None:
    token = await api_login(client, child_user.email, "child-pass")
    response = await client.get(
        "/api/v1/c/not-a-real-token",
        headers=auth_header(token),
    )
    assert response.status_code == 404
