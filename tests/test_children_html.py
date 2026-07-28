"""HTML Children routes: CRUD, validation errors, activate/deactivate."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from conftest import create_user
from qr_chores.models.user import User, UserRole


async def _login_parent(client: AsyncClient, parent: User) -> None:
    r = await client.post(
        "/login",
        data={"email": parent.email, "password": "parent-pass", "next": ""},
        follow_redirects=False,
    )
    assert r.status_code in (303, 302)


@pytest.mark.asyncio
async def test_children_new_form(client: AsyncClient, parent_user: User) -> None:
    await _login_parent(client, parent_user)
    page = await client.get("/children/new")
    assert page.status_code == 200
    assert "Add child" in page.text or "child" in page.text.lower()
    assert 'name="email"' in page.text
    assert 'name="password"' in page.text


@pytest.mark.asyncio
async def test_children_create_validation_error(client: AsyncClient, parent_user: User) -> None:
    await _login_parent(client, parent_user)
    # missing password → UserServiceError → re-render form with 400
    bad = await client.post(
        "/children",
        data={
            "email": "bad-kid@example.com",
            "password": "",
            "first_name": "Bad",
            "last_name": "Kid",
        },
        follow_redirects=False,
    )
    assert bad.status_code == 400
    assert "Password" in bad.text or "required" in bad.text.lower()


@pytest.mark.asyncio
async def test_children_create_duplicate_username(
    client: AsyncClient, parent_user: User, child_user: User
) -> None:
    await _login_parent(client, parent_user)
    dup = await client.post(
        "/children",
        data={
            "email": child_user.email,
            "password": "child-pass",
            "first_name": "Dup",
            "last_name": "Kid",
        },
        follow_redirects=False,
    )
    assert dup.status_code == 400
    assert "taken" in dup.text.lower() or "already" in dup.text.lower()


@pytest.mark.asyncio
async def test_children_edit_form_and_save(
    client: AsyncClient, parent_user: User, child_user: User
) -> None:
    await _login_parent(client, parent_user)
    form = await client.get(f"/children/{child_user.id}/edit")
    assert form.status_code == 200
    assert child_user.email in form.text
    assert child_user.first_name in form.text

    saved = await client.post(
        f"/children/{child_user.id}/edit",
        data={
            "email": child_user.email,
            "first_name": "Renamed",
            "last_name": "Kid",
            "password": "",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"] == "/children"

    listed = await client.get("/children")
    assert "Renamed Kid" in listed.text


@pytest.mark.asyncio
async def test_children_edit_with_password_and_validation_error(
    client: AsyncClient, parent_user: User, child_user: User, app
) -> None:
    await _login_parent(client, parent_user)
    # Create a second child so rename-to-existing email can conflict
    other = await create_user(
        app.state.session_factory,
        email="other-kid@example.com",
        first_name="Other",
        last_name="Kid",
        password="child-pass",
        role=UserRole.child,
        parent_id=parent_user.id,
    )

    conflict = await client.post(
        f"/children/{child_user.id}/edit",
        data={
            "email": other.email,
            "first_name": "X",
            "last_name": "Y",
            "password": "new-pass-ok",
        },
        follow_redirects=False,
    )
    assert conflict.status_code == 400
    assert "taken" in conflict.text.lower() or "already" in conflict.text.lower()

    # successful password change
    ok = await client.post(
        f"/children/{child_user.id}/edit",
        data={
            "email": "renamed-email@example.com",
            "first_name": "New",
            "last_name": "Name",
            "password": "brand-new-pass",
        },
        follow_redirects=False,
    )
    assert ok.status_code == 303

    # login as child with new credentials
    await client.post("/logout", follow_redirects=False)
    login = await client.post(
        "/login",
        data={"email": "renamed-email@example.com", "password": "brand-new-pass", "next": ""},
        follow_redirects=False,
    )
    assert login.status_code in (303, 302)


@pytest.mark.asyncio
async def test_children_edit_missing_redirects(client: AsyncClient, parent_user: User) -> None:
    await _login_parent(client, parent_user)
    missing_get = await client.get("/children/999999/edit", follow_redirects=False)
    assert missing_get.status_code == 303
    assert missing_get.headers["location"] == "/children"

    missing_post = await client.post(
        "/children/999999/edit",
        data={
            "email": "x@y.z",
            "first_name": "X",
            "last_name": "Y",
            "password": "",
        },
        follow_redirects=False,
    )
    assert missing_post.status_code == 303
    assert missing_post.headers["location"] == "/children"


@pytest.mark.asyncio
async def test_children_deactivate_and_activate(
    client: AsyncClient, parent_user: User, child_user: User
) -> None:
    await _login_parent(client, parent_user)

    deact = await client.post(
        f"/children/{child_user.id}/deactivate",
        follow_redirects=False,
    )
    assert deact.status_code == 303
    assert deact.headers["location"] == "/children"

    listed = await client.get("/children")
    assert listed.status_code == 200
    # inactive kids still listed (include_inactive=True)
    assert child_user.display_name.split()[0] in listed.text or "Daughter" in listed.text

    act = await client.post(
        f"/children/{child_user.id}/activate",
        follow_redirects=False,
    )
    assert act.status_code == 303

    # missing id still redirects (no-op)
    noop = await client.post("/children/999999/deactivate", follow_redirects=False)
    assert noop.status_code == 303
    noop2 = await client.post("/children/999999/activate", follow_redirects=False)
    assert noop2.status_code == 303


@pytest.mark.asyncio
async def test_children_routes_require_parent(client: AsyncClient, child_user: User) -> None:
    await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
        follow_redirects=False,
    )
    forbidden = await client.get("/children")
    assert forbidden.status_code in (403, 303, 401)
