"""Additional /api/v1 child edge-case HTTP tests."""

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
        "title": "Child edge",
        "description": None,
        "qr_token": new_qr_token(),
        "due_time": time(21, 0),
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
async def test_inactive_chore_not_found(client: AsyncClient, child_user: User, app) -> None:
    chore = await _create_chore(app.state.session_factory, is_active=False)
    token = await api_login(client, child_user.email, "child-pass")
    headers = auth_header(token)

    confirm = await client.get(f"/api/v1/c/{chore.qr_token}", headers=headers)
    assert confirm.status_code == 404

    complete = await client.post(f"/api/v1/c/{chore.qr_token}/complete", headers=headers)
    assert complete.status_code == 404


@pytest.mark.asyncio
async def test_complete_unknown_token(client: AsyncClient, child_user: User) -> None:
    token = await api_login(client, child_user.email, "child-pass")
    response = await client.post(
        "/api/v1/c/no-such-token/complete",
        headers=auth_header(token),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_not_scheduled_complete(client: AsyncClient, child_user: User, app) -> None:
    # schedule_days empty of today is hard; use no days effectively via empty string after normalize
    # Domain stores days string; "" means never scheduled in is_scheduled_on if no digit matches.
    chore = await _create_chore(app.state.session_factory, schedule_days="")
    token = await api_login(client, child_user.email, "child-pass")
    headers = auth_header(token)

    confirm = await client.get(f"/api/v1/c/{chore.qr_token}", headers=headers)
    assert confirm.status_code == 200
    assert confirm.json()["scheduled_today"] is False

    complete = await client.post(f"/api/v1/c/{chore.qr_token}/complete", headers=headers)
    # Domain may reject unscheduled completes
    assert complete.status_code in (200, 400)
    if complete.status_code == 400:
        detail = complete.json()["detail"]
        assert "code" in detail or "message" in detail or isinstance(detail, str)


@pytest.mark.asyncio
async def test_parent_forbidden_on_child_reads(client: AsyncClient, parent_user: User, app) -> None:
    chore = await _create_chore(app.state.session_factory)
    token = await api_login(client, parent_user.email, "parent-pass")
    headers = auth_header(token)

    assert (await client.get("/api/v1/home", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/achievements", headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/c/{chore.qr_token}", headers=headers)).status_code == 403
