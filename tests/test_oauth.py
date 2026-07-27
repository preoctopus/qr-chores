"""Unit tests for backend OAuth 2.1 store (oauth_store.py) and OAuth models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from qr_chores.services import oauth_store
from qr_chores.services.oauth_store import _json_dumps, _json_loads


def test_oauth_json_helpers() -> None:
    assert _json_dumps(["a", "b"]) == '["a", "b"]'
    assert _json_dumps({"x": 1}) == '{"x": 1}'
    assert _json_loads('["read", "write"]') == ["read", "write"]
    assert _json_loads("not-json") == []
    assert _json_loads('{"not": "a list"}') == []
    assert _json_loads("[1, 2]") == ["1", "2"]


@pytest.mark.asyncio
async def test_oauth_client_crud(db_session):
    client = await oauth_store.save_oauth_client(
        session=db_session,
        client_id="test-client-1",
        client_secret="test-secret-1",
        client_name="Test OAuth App",
        redirect_uris=["https://example.com/callback"],
        grant_types=["authorization_code"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )
    assert client.client_id == "test-client-1"

    fetched = await oauth_store.get_oauth_client(db_session, "test-client-1")
    assert fetched is not None
    assert fetched.client_name == "Test OAuth App"

    # update existing client (including secret)
    updated = await oauth_store.save_oauth_client(
        session=db_session,
        client_id="test-client-1",
        client_secret="rotated-secret",
        client_name="Renamed App",
        redirect_uris=["https://example.com/cb2"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="client_secret_post",
    )
    assert updated.client_name == "Renamed App"
    assert updated.client_secret == "rotated-secret"
    assert updated.token_endpoint_auth_method == "client_secret_post"

    # update without rotating secret
    again = await oauth_store.save_oauth_client(
        session=db_session,
        client_id="test-client-1",
        client_name="Still Renamed",
        redirect_uris=["https://example.com/cb2"],
        grant_types=["authorization_code"],
        response_types=["code"],
        client_secret=None,
    )
    assert again.client_secret == "rotated-secret"
    assert again.client_name == "Still Renamed"

    missing = await oauth_store.get_oauth_client(db_session, "nonexistent")
    assert missing is None


@pytest.mark.asyncio
async def test_oauth_code_crud(db_session):
    exp = datetime.now(UTC) + timedelta(minutes=10)
    code = await oauth_store.create_oauth_code(
        session=db_session,
        code="code-123",
        client_id="test-client-1",
        user_id=1,
        redirect_uri="https://example.com/callback",
        code_challenge="challenge-123",
        code_challenge_method="S256",
        scopes=["read"],
        expires_at=exp,
    )
    assert code.code == "code-123"

    fetched = await oauth_store.get_oauth_code(db_session, "code-123")
    assert fetched is not None
    assert fetched.user_id == 1

    await oauth_store.delete_oauth_code(db_session, "code-123")
    deleted = await oauth_store.get_oauth_code(db_session, "code-123")
    assert deleted is None


@pytest.mark.asyncio
async def test_oauth_code_and_token_naive_expires_at(db_session):
    """Naive datetimes are accepted (normalized to UTC before insert)."""
    naive = datetime(2099, 1, 1, 12, 0, 0)  # intentionally tz-naive
    assert naive.tzinfo is None
    code = await oauth_store.create_oauth_code(
        session=db_session,
        code="code-naive",
        client_id="test-client-1",
        user_id=1,
        redirect_uri="https://example.com/callback",
        code_challenge="chal",
        code_challenge_method="S256",
        scopes=["read"],
        expires_at=naive,
    )
    assert code.code == "code-naive"

    token = await oauth_store.create_oauth_token(
        session=db_session,
        access_token="access-naive",
        refresh_token="refresh-naive",
        client_id="test-client-1",
        user_id=1,
        scopes=["read"],
        expires_at=naive,
    )
    assert token.access_token == "access-naive"

    # revoke via refresh token path
    await oauth_store.revoke_oauth_token(db_session, "refresh-naive")
    assert await oauth_store.get_oauth_token(db_session, "access-naive") is None
    assert await oauth_store.get_oauth_token_by_refresh(db_session, "refresh-naive") is None


@pytest.mark.asyncio
async def test_oauth_token_crud_and_revocation(db_session):
    exp = datetime.now(UTC) + timedelta(hours=1)
    token = await oauth_store.create_oauth_token(
        session=db_session,
        access_token="access-123",
        refresh_token="refresh-123",
        client_id="test-client-1",
        user_id=1,
        scopes=["read", "write"],
        expires_at=exp,
    )
    assert token.access_token == "access-123"

    fetched_acc = await oauth_store.get_oauth_token(db_session, "access-123")
    assert fetched_acc is not None
    assert fetched_acc.user_id == 1

    fetched_ref = await oauth_store.get_oauth_token_by_refresh(db_session, "refresh-123")
    assert fetched_ref is not None
    assert fetched_ref.access_token == "access-123"

    await oauth_store.revoke_oauth_token(db_session, "access-123")
    revoked = await oauth_store.get_oauth_token(db_session, "access-123")
    assert revoked is None
