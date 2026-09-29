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
async def test_root_redirects_logged_in_parent_and_child(
    client: AsyncClient, parent_user: User, child_user: User
) -> None:
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
        follow_redirects=False,
    )
    parent_root = await client.get("/", follow_redirects=False)
    assert parent_root.status_code == 303
    assert parent_root.headers["location"] == "/today"

    await client.post("/logout", follow_redirects=False)
    await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
        follow_redirects=False,
    )
    child_root = await client.get("/", follow_redirects=False)
    assert child_root.status_code == 303
    assert child_root.headers["location"] == "/home"


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
    assert f"Hey, {parent_user.first_name}" in response.text
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
    assert f"Hey, {child_user.first_name}" in response.text
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
async def test_logout_clears_session(client: AsyncClient, parent_user: User) -> None:
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
async def test_logout_rejects_get(client: AsyncClient, parent_user: User) -> None:
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )
    response = await client.get("/logout", follow_redirects=False)
    assert response.status_code == 405
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
    response = await client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert (await client.get("/me")).status_code == 401


@pytest.mark.asyncio
async def test_login_hashes_even_for_unknown_email(
    client: AsyncClient, parent_user: User, monkeypatch
) -> None:
    """Unknown and known emails must both pay one argon2 verification.

    Otherwise the response-time difference (~30x) is an account-enumeration
    oracle revealing which family emails are registered.
    """
    from qr_chores.auth import passwords

    real = passwords._password_hash
    calls: list[str] = []

    class CountingHash:
        def verify(self, password: str, password_hash: str) -> bool:
            calls.append(password_hash)
            return real.verify(password, password_hash)

    monkeypatch.setattr(passwords, "_password_hash", CountingHash())

    await client.post("/login", data={"email": "nobody@example.com", "password": "x"})
    unknown_calls = len(calls)

    calls.clear()
    await client.post("/login", data={"email": parent_user.email, "password": "x"})
    known_calls = len(calls)

    assert unknown_calls == known_calls == 1


@pytest.mark.asyncio
async def test_api_login_hashes_even_for_unknown_email(
    client: AsyncClient, parent_user: User, monkeypatch
) -> None:
    from qr_chores.auth import passwords

    real = passwords._password_hash
    calls: list[str] = []

    class CountingHash:
        def verify(self, password: str, password_hash: str) -> bool:
            calls.append(password_hash)
            return real.verify(password, password_hash)

    monkeypatch.setattr(passwords, "_password_hash", CountingHash())

    await client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"})
    unknown_calls = len(calls)

    calls.clear()
    await client.post("/api/v1/auth/login", json={"email": parent_user.email, "password": "x"})
    known_calls = len(calls)

    assert unknown_calls == known_calls == 1
