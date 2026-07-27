"""Internal /api/v1 auth tests."""

import pytest
from httpx import AsyncClient

from qr_chores.models.user import User

PROTECTED = (
    "/api/v1/me",
    "/api/v1/home",
    "/api/v1/achievements",
    "/api/v1/c/some-token",
    "/api/v1/today",
    "/api/v1/history",
    "/api/v1/chores",
    "/api/v1/rewards",
)


async def api_login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    return body["access_token"]


@pytest.mark.asyncio
async def test_api_login_success(client: AsyncClient, child_user: User) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": child_user.email, "password": "child-pass"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == child_user.email
    assert data["user"]["role"] == "child"
    assert "points_balance" in data["user"]
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_api_login_bad_password(client: AsyncClient, child_user: User) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": child_user.email, "password": "wrong"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_protected_endpoints_require_auth(client: AsyncClient) -> None:
    """Unauthenticated calls to protected routes must return 401 JSON."""
    for path in PROTECTED:
        response = await client.get(path)
        assert response.status_code == 401, path
        body = response.json()
        assert "detail" in body
        # Must not HTML-redirect to login
        assert response.headers.get("content-type", "").startswith("application/json")


@pytest.mark.asyncio
async def test_complete_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/v1/c/some-token/complete")
    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_bearer_malformed_and_session_as_bearer(
    client: AsyncClient, child_user: User, test_settings
) -> None:
    """Non-Bearer schemes ignored; session cookie value accepted as Bearer."""
    from qr_chores.auth.session import dump_session

    bad = await client.get("/api/v1/me", headers={"Authorization": "Basic xyz"})
    assert bad.status_code == 401
    empty = await client.get("/api/v1/me", headers={"Authorization": "Bearer "})
    assert empty.status_code == 401

    # Session-salt token accepted as Bearer (compat path in deps)
    session_token = dump_session(test_settings, child_user.id)
    me = await client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == child_user.email


@pytest.mark.asyncio
async def test_me_with_bearer(client: AsyncClient, child_user: User) -> None:
    token = await api_login(client, child_user.email, "child-pass")
    response = await client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == child_user.id
    assert data["role"] == "child"


@pytest.mark.asyncio
async def test_me_with_invalid_bearer(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_cookie(client: AsyncClient, child_user: User) -> None:
    await api_login(client, child_user.email, "child-pass")
    # Cookie-based me after login
    me = await client.get("/api/v1/me")
    assert me.status_code == 200

    logout = await client.post("/api/v1/auth/logout")
    assert logout.status_code == 204

    me_after = await client.get("/api/v1/me")
    assert me_after.status_code == 401
