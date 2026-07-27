"""Admin registration + parent children API + assignee isolation."""

from datetime import time

import pytest
from httpx import AsyncClient

from conftest import create_user
from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.models.user import User, UserRole
from qr_chores.services.qr import new_qr_token


async def api_login(client: AsyncClient, email: str, password: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_register_parent(client: AsyncClient, test_settings, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    from qr_chores.config import get_settings

    get_settings.cache_clear()

    missing = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "admin-created@example.com",
            "password": "parent-pass",
            "first_name": "Alex",
            "last_name": "Admin",
        },
    )
    assert missing.status_code == 401

    created = await client.post(
        "/api/v1/admin/users",
        headers={"X-Admin-Key": "test-admin-key"},
        json={
            "email": "Admin-Created@example.com",
            "password": "parent-pass",
            "first_name": "Alex",
            "last_name": "Admin",
            "role": "parent",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] == "admin-created@example.com"
    assert body["first_name"] == "Alex"
    assert body["last_name"] == "Admin"
    assert body["display_name"] == "Alex Admin"
    assert body["role"] == "parent"
    assert body["parent_id"] is None

    # login works with registered credentials
    token = await api_login(client, "admin-created@example.com", "parent-pass")
    me = await client.get("/api/v1/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["first_name"] == "Alex"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_admin_disabled_without_key(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_API_KEY", "")
    from qr_chores.config import get_settings

    get_settings.cache_clear()
    r = await client.post(
        "/api/v1/admin/users",
        headers={"X-Admin-Key": "anything"},
        json={
            "email": "x@y.z",
            "password": "p",
            "first_name": "X",
            "last_name": "Y",
        },
    )
    assert r.status_code == 503
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_parent_manages_children(client: AsyncClient, parent_user: User, app) -> None:
    token = await api_login(client, parent_user.email, "parent-pass")
    headers = auth(token)

    created = await client.post(
        "/api/v1/children",
        headers=headers,
        json={
            "email": "sam@example.com",
            "password": "child-pass",
            "first_name": "Sam",
            "last_name": "Kid",
        },
    )
    assert created.status_code == 201, created.text
    child = created.json()
    assert child["role"] == "child"
    assert child["parent_id"] == parent_user.id
    assert child["display_name"] == "Sam Kid"
    child_id = child["id"]

    listed = await client.get("/api/v1/children", headers=headers)
    assert listed.status_code == 200
    assert any(c["id"] == child_id for c in listed.json()["children"])

    patched = await client.patch(
        f"/api/v1/children/{child_id}",
        headers=headers,
        json={"first_name": "Sammy"},
    )
    assert patched.status_code == 200
    assert patched.json()["display_name"] == "Sammy Kid"

    deact = await client.post(f"/api/v1/children/{child_id}/deactivate", headers=headers)
    assert deact.status_code == 200
    assert deact.json()["is_active"] is False

    act = await client.post(f"/api/v1/children/{child_id}/activate", headers=headers)
    assert act.status_code == 200
    assert act.json()["is_active"] is True


@pytest.mark.asyncio
async def test_sibling_cannot_complete_other_child_chore(
    client: AsyncClient, parent_user: User, child_user: User, app
) -> None:
    sibling = await create_user(
        app.state.session_factory,
        email="sib@example.com",
        first_name="Sib",
        last_name="Ling",
        password="child-pass",
        role=UserRole.child,
        parent_id=parent_user.id,
    )
    async with app.state.session_factory() as session:
        chore = Chore(
            title="Only for daughter",
            description=None,
            qr_token=new_qr_token(),
            due_time=time(23, 59),
            schedule_days="0123456",
            photo_policy=PhotoPolicy.none,
            base_points=5,
            is_active=True,
            assignee_user_id=child_user.id,
        )
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        token_str = chore.qr_token

    sib_token = await api_login(client, sibling.email, "child-pass")
    forbidden = await client.post(
        f"/api/v1/c/{token_str}/complete",
        headers=auth(sib_token),
    )
    assert forbidden.status_code == 403

    child_token = await api_login(client, child_user.email, "child-pass")
    ok = await client.post(
        f"/api/v1/c/{token_str}/complete",
        headers=auth(child_token),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["already_done"] is False


@pytest.mark.asyncio
async def test_html_children_page(client: AsyncClient, parent_user: User) -> None:
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
        follow_redirects=False,
    )
    page = await client.get("/children")
    assert page.status_code == 200
    assert "Children" in page.text

    created = await client.post(
        "/children",
        data={
            "email": "html-kid@example.com",
            "password": "child-pass",
            "first_name": "Html",
            "last_name": "Kid",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    listed = await client.get("/children")
    assert "Html Kid" in listed.text
