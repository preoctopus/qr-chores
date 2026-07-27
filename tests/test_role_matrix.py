"""Exhaustive role authorization matrix (HTML + API).

One place that asserts parent-only vs child-only boundaries so new routes
are less likely to slip through without a 403 check.
"""

from __future__ import annotations

from datetime import time

import pytest
from httpx import AsyncClient

from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.models.user import User
from qr_chores.services.qr import new_qr_token

# Parent-only HTML routes (GET unless noted). Child must receive 403.
PARENT_HTML_GET = (
    "/today",
    "/history",
    "/chores",
    "/chores/new",
    "/rewards",
    "/rewards/achievements/new",
    "/print/qrs",
)

# Child-only HTML routes. Parent must receive 403.
CHILD_HTML_GET = (
    "/home",
    "/me/achievements",
)

# Parent-only API GETs. Child → 403; anon → 401.
PARENT_API_GET = (
    "/api/v1/today",
    "/api/v1/history",
    "/api/v1/chores",
    "/api/v1/rewards",
)

# Child-only API GETs. Parent → 403; anon → 401.
CHILD_API_GET = (
    "/api/v1/home",
    "/api/v1/achievements",
)


async def _html_login(client: AsyncClient, email: str, password: str) -> None:
    await client.post(
        "/login",
        data={"email": email, "password": password, "next": ""},
    )


async def _api_login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_chore(session_factory, **kwargs) -> Chore:
    defaults = {
        "title": "Role matrix chore",
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


# ---------------------------------------------------------------------------
# HTML role boundaries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PARENT_HTML_GET)
async def test_child_forbidden_on_parent_html_gets(
    client: AsyncClient, child_user: User, path: str
) -> None:
    await _html_login(client, child_user.email, "child-pass")
    response = await client.get(path)
    assert response.status_code == 403, path


@pytest.mark.asyncio
@pytest.mark.parametrize("path", CHILD_HTML_GET)
async def test_parent_forbidden_on_child_html_gets(
    client: AsyncClient, parent_user: User, path: str
) -> None:
    await _html_login(client, parent_user.email, "parent-pass")
    response = await client.get(path)
    assert response.status_code == 403, path


@pytest.mark.asyncio
async def test_child_forbidden_on_parent_html_mutations(
    client: AsyncClient, child_user: User, app
) -> None:
    chore = await _create_chore(app.state.session_factory)
    await _html_login(client, child_user.email, "child-pass")

    create = await client.post(
        "/chores",
        data={
            "title": "Hacked",
            "description": "",
            "due_time": "20:00",
            "base_points": "1",
            "photo_policy": "none",
            "schedule_day": ["0"],
        },
    )
    assert create.status_code == 403

    edit = await client.post(
        f"/chores/{chore.id}/edit",
        data={
            "title": "Hacked",
            "description": "",
            "due_time": "20:00",
            "base_points": "1",
            "photo_policy": "none",
            "schedule_day": ["0"],
        },
    )
    assert edit.status_code == 403

    for path in (
        f"/chores/{chore.id}/deactivate",
        f"/chores/{chore.id}/activate",
        f"/chores/{chore.id}/delete",
    ):
        assert (await client.post(path)).status_code == 403, path

    assert (await client.get(f"/chores/{chore.id}/qr")).status_code == 403
    assert (await client.get(f"/chores/{chore.id}/qr.png")).status_code == 403
    assert (await client.get(f"/chores/{chore.id}/delete")).status_code == 403
    assert (await client.get(f"/chores/{chore.id}/edit")).status_code == 403

    bonuses = await client.post(
        "/rewards/bonuses",
        data={
            "early_bonus_points": "9",
            "on_time_bonus_points": "9",
            "late_bonus_points": "0",
        },
    )
    assert bonuses.status_code == 403

    ach = await client.post(
        "/rewards/achievements",
        data={
            "title": "Nope",
            "description": "",
            "icon_key": "star",
            "criteria_type": "total_completions",
            "threshold": "1",
            "points_reward": "1",
        },
    )
    assert ach.status_code == 403


@pytest.mark.asyncio
async def test_parent_forbidden_on_child_complete_html(
    client: AsyncClient, parent_user: User, app
) -> None:
    chore = await _create_chore(app.state.session_factory)
    await _html_login(client, parent_user.email, "parent-pass")
    assert (await client.get(f"/c/{chore.qr_token}")).status_code == 403
    assert (await client.post(f"/c/{chore.qr_token}")).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_html_parent_routes_redirect_to_login(client: AsyncClient) -> None:
    for path in PARENT_HTML_GET:
        response = await client.get(path, follow_redirects=False)
        assert response.status_code in (303, 401, 403), path
        if response.status_code == 303:
            assert "/login" in response.headers["location"]


# ---------------------------------------------------------------------------
# API role boundaries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PARENT_API_GET)
async def test_child_forbidden_on_parent_api_gets(
    client: AsyncClient, child_user: User, path: str
) -> None:
    token = await _api_login(client, child_user.email, "child-pass")
    response = await client.get(path, headers=_auth(token))
    assert response.status_code == 403, path
    assert "detail" in response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", CHILD_API_GET)
async def test_parent_forbidden_on_child_api_gets(
    client: AsyncClient, parent_user: User, path: str
) -> None:
    token = await _api_login(client, parent_user.email, "parent-pass")
    response = await client.get(path, headers=_auth(token))
    assert response.status_code == 403, path
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_child_forbidden_on_parent_api_mutations(
    client: AsyncClient, child_user: User, app
) -> None:
    chore = await _create_chore(app.state.session_factory)
    token = await _api_login(client, child_user.email, "child-pass")
    headers = _auth(token)

    assert (
        await client.post(
            "/api/v1/chores",
            headers=headers,
            json={
                "title": "Nope",
                "due_time": "10:00:00",
                "photo_policy": "none",
                "base_points": 1,
            },
        )
    ).status_code == 403

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
    assert (
        await client.post(f"/api/v1/chores/{chore.id}/activate", headers=headers)
    ).status_code == 403
    assert (await client.delete(f"/api/v1/chores/{chore.id}", headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/chores/{chore.id}", headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/chores/{chore.id}/qr", headers=headers)).status_code == 403
    assert (
        await client.get(f"/api/v1/chores/{chore.id}/qr.png", headers=headers)
    ).status_code == 403

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
    assert (
        await client.post(
            "/api/v1/rewards/achievements",
            headers=headers,
            json={
                "title": "Nope",
                "description": "",
                "icon_key": "star",
                "criteria_type": "total_completions",
                "threshold": 1,
                "points_reward": 1,
            },
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_parent_forbidden_on_child_api_complete(
    client: AsyncClient, parent_user: User, app
) -> None:
    chore = await _create_chore(app.state.session_factory)
    token = await _api_login(client, parent_user.email, "parent-pass")
    headers = _auth(token)
    assert (await client.get(f"/api/v1/c/{chore.qr_token}", headers=headers)).status_code == 403
    assert (
        await client.post(f"/api/v1/c/{chore.qr_token}/complete", headers=headers)
    ).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_api_returns_json_401(client: AsyncClient, app) -> None:
    chore = await _create_chore(app.state.session_factory)
    paths = [
        *PARENT_API_GET,
        *CHILD_API_GET,
        "/api/v1/me",
        f"/api/v1/c/{chore.qr_token}",
        f"/api/v1/chores/{chore.id}",
    ]
    for path in paths:
        response = await client.get(path)
        assert response.status_code == 401, path
        assert response.headers.get("content-type", "").startswith("application/json")
        assert "detail" in response.json()

    post = await client.post(f"/api/v1/c/{chore.qr_token}/complete")
    assert post.status_code == 401
    assert post.headers.get("content-type", "").startswith("application/json")
