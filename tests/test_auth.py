"""Authentication and role routing tests."""

import pytest
from httpx import AsyncClient

from qr_chores.models.user import User


@pytest.mark.asyncio
async def test_root_redirects_to_login_when_anonymous(client: AsyncClient) -> None:
    response = await client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_login_page_renders(client: AsyncClient) -> None:
    response = await client.get("/login")
    assert response.status_code == 200
    assert "Log in" in response.text or "Welcome back" in response.text


@pytest.mark.asyncio
async def test_login_rejects_bad_credentials(client: AsyncClient, parent_user: User) -> None:
    response = await client.post(
        "/login",
        data={"email": parent_user.email, "password": "wrong-password", "next": ""},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.text


@pytest.mark.asyncio
async def test_parent_login_redirects_to_today(client: AsyncClient, parent_user: User) -> None:
    response = await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/today"
    assert "qr_chores_session" in response.cookies


@pytest.mark.asyncio
async def test_child_login_redirects_to_home(client: AsyncClient, child_user: User) -> None:
    response = await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/home"


@pytest.mark.asyncio
async def test_parent_can_access_today(client: AsyncClient, parent_user: User) -> None:
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )
    response = await client.get("/today")
    assert response.status_code == 200
    assert "Today" in response.text
    assert parent_user.display_name in response.text


@pytest.mark.asyncio
async def test_child_forbidden_on_parent_today(client: AsyncClient, child_user: User) -> None:
    await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
    )
    response = await client.get("/today")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_parent_forbidden_on_child_home(client: AsyncClient, parent_user: User) -> None:
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )
    response = await client.get("/home")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_child_can_access_home(client: AsyncClient, child_user: User) -> None:
    await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
    )
    response = await client.get("/home")
    assert response.status_code == 200
    assert child_user.display_name in response.text


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user(client: AsyncClient, parent_user: User) -> None:
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )
    response = await client.get("/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == parent_user.email
    assert data["role"] == "parent"
    assert data["display_name"] == parent_user.display_name


@pytest.mark.asyncio
async def test_get_logout_is_not_allowed(client: AsyncClient, parent_user: User) -> None:
    """State-changing logout must not work via GET (prefetch / CSRF-by-img)."""
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )
    assert (await client.get("/me")).status_code == 200
    response = await client.get("/logout", follow_redirects=False)
    assert response.status_code == 405
    # Session still valid after GET
    assert (await client.get("/me")).status_code == 200


@pytest.mark.asyncio
async def test_login_next_blocks_open_redirect(client: AsyncClient, parent_user: User) -> None:
    response = await client.post(
        "/login",
        data={
            "email": parent_user.email,
            "password": "parent-pass",
            "next": "https://evil.example/phish",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    # Falls back to role home, not external URL
    assert response.headers["location"] == "/today"


@pytest.mark.asyncio
async def test_login_next_blocks_triple_slash_redirect(
    client: AsyncClient, parent_user: User
) -> None:
    response = await client.post(
        "/login",
        data={
            "email": parent_user.email,
            "password": "parent-pass",
            "next": "///evil.example/phish",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/today"


@pytest.mark.asyncio
async def test_login_next_allows_relative(client: AsyncClient, parent_user: User) -> None:
    response = await client.post(
        "/login",
        data={
            "email": parent_user.email,
            "password": "parent-pass",
            "next": "/me",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/me"


@pytest.mark.asyncio
async def test_login_page_redirects_when_already_authed(
    client: AsyncClient, parent_user: User
) -> None:
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )
    response = await client.get("/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/today"


@pytest.mark.asyncio
async def test_post_logout(client: AsyncClient, parent_user: User) -> None:
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )
    assert (await client.get("/me")).status_code == 200
    response = await client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert (await client.get("/me")).status_code == 401


@pytest.mark.asyncio
async def test_nav_logout_is_post_form(client: AsyncClient, parent_user: User) -> None:
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )
    response = await client.get("/today")
    assert response.status_code == 200
    html = response.text
    assert 'method="post"' in html
    assert 'action="/logout"' in html
    assert 'href="/logout"' not in html
