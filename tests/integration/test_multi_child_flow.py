"""Integration: admin parent → children → assigned chores → isolation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from conftest import create_user
from integration.helpers import api_login, auth_header, html_login, seed_chore
from qr_chores.models.user import UserRole


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_child_registration_and_isolation(
    client: AsyncClient, app, monkeypatch
) -> None:
    monkeypatch.setenv("ADMIN_API_KEY", "integ-admin-key")
    from qr_chores.config import get_settings

    get_settings.cache_clear()

    # Admin registers a parent
    reg = await client.post(
        "/api/v1/admin/users",
        headers={"X-Admin-Key": "integ-admin-key"},
        json={
            "email": "family.parent@example.com",
            "password": "parent-pass",
            "first_name": "Fran",
            "last_name": "Parent",
            "role": "parent",
        },
    )
    assert reg.status_code == 201, reg.text
    parent_id = reg.json()["id"]

    ptoken = await api_login(client, "family.parent@example.com", "parent-pass")
    headers = auth_header(ptoken)

    # Parent creates two children
    c1 = await client.post(
        "/api/v1/children",
        headers=headers,
        json={
            "email": "kid.a@example.com",
            "password": "child-pass",
            "first_name": "Kid",
            "last_name": "A",
        },
    )
    c2 = await client.post(
        "/api/v1/children",
        headers=headers,
        json={
            "email": "kid.b@example.com",
            "password": "child-pass",
            "first_name": "Kid",
            "last_name": "B",
        },
    )
    assert c1.status_code == 201 and c2.status_code == 201
    kid_a_id = c1.json()["id"]
    kid_b_id = c2.json()["id"]
    assert c1.json()["parent_id"] == parent_id

    # Chores assigned per child
    chore_a = await client.post(
        "/api/v1/chores",
        headers=headers,
        json={
            "title": "A dishes",
            "due_time": "23:59:00",
            "schedule_days": "0123456",
            "photo_policy": "none",
            "base_points": 5,
            "assignee_user_id": kid_a_id,
        },
    )
    chore_b = await client.post(
        "/api/v1/chores",
        headers=headers,
        json={
            "title": "B laundry",
            "due_time": "23:59:00",
            "schedule_days": "0123456",
            "photo_policy": "none",
            "base_points": 7,
            "assignee_user_id": kid_b_id,
        },
    )
    assert chore_a.status_code == 201 and chore_b.status_code == 201
    token_a = chore_a.json()["qr_token"]
    token_b = chore_b.json()["qr_token"]

    # Parent today shows both
    today = await client.get("/api/v1/today", headers=headers)
    assert today.status_code == 200
    titles = {row["chore"]["title"] for row in today.json()["board"]}
    assert titles == {"A dishes", "B laundry"}

    # Child A home only sees A chores
    atoken = await api_login(client, "kid.a@example.com", "child-pass")
    home_a = await client.get("/api/v1/home", headers=auth_header(atoken))
    assert home_a.status_code == 200
    a_titles = {row["chore"]["title"] for row in home_a.json()["board"]}
    assert a_titles == {"A dishes"}

    # Child B cannot complete A's chore
    btoken = await api_login(client, "kid.b@example.com", "child-pass")
    steal = await client.post(
        f"/api/v1/c/{token_a}/complete",
        headers=auth_header(btoken),
    )
    assert steal.status_code == 403

    # Child A can complete own
    done = await client.post(
        f"/api/v1/c/{token_a}/complete",
        headers=auth_header(atoken),
    )
    assert done.status_code == 200
    assert done.json()["already_done"] is False

    # Child B completes own
    done_b = await client.post(
        f"/api/v1/c/{token_b}/complete",
        headers=auth_header(btoken),
    )
    assert done_b.status_code == 200

    # HTML parent children management
    await html_login(client, "family.parent@example.com", "parent-pass")
    page = await client.get("/children")
    assert page.status_code == 200
    assert "Kid A" in page.text and "Kid B" in page.text

    get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_chore_assignee_blocks_sibling(
    client: AsyncClient, parent_user, child_user, app
) -> None:
    other = await create_user(
        app.state.session_factory,
        email="other-kid@example.com",
        first_name="Other",
        last_name="Kid",
        password="child-pass",
        role=UserRole.child,
        parent_id=parent_user.id,
    )
    chore = await seed_chore(
        app.state.session_factory,
        title="Assigned chore",
        assignee_user_id=child_user.id,
    )
    other_token = await api_login(client, other.email, "child-pass")
    r = await client.post(
        f"/api/v1/c/{chore.qr_token}/complete",
        headers=auth_header(other_token),
    )
    assert r.status_code == 403
