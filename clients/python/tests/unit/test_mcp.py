"""MCP server registration and tool call smoke tests."""

from __future__ import annotations

import base64
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport
from tests.conftest import CHILD_EMAIL, CHILD_PASSWORD, PARENT_EMAIL, PARENT_PASSWORD, TINY_PNG

from qr_chores_client import QrChoresClient, mcp_server
from qr_chores_client.mcp_server import (
    ClientHolder,
    _to_jsonable,
    create_mcp_server,
    list_tool_names,
)
from qr_chores_client.models import User


def test_list_tool_names_includes_contract_methods():
    names = set(list_tool_names())
    expected = {
        "login",
        "logout",
        "get_me",
        "get_home",
        "get_confirm",
        "complete_chore",
        "get_achievements",
        "get_today",
        "get_history",
        "get_history_days",
        "list_children",
        "create_child",
        "get_child",
        "update_child",
        "activate_child",
        "deactivate_child",
        "list_chores",
        "create_chore",
        "get_chore",
        "update_chore",
        "delete_chore",
        "activate_chore",
        "deactivate_chore",
        "get_qr_info",
        "get_qr_png",
        "get_rewards",
        "update_bonuses",
        "create_achievement",
        "update_achievement",
        "toggle_achievement",
        "get_photo",
    }
    assert expected.issubset(names)


def test_create_mcp_server_returns_instance():
    server = create_mcp_server()
    assert server is not None


def test_to_jsonable_model_and_bytes():
    user = User(
        id=1,
        email="a@b.c",
        display_name="A",
        role="parent",
        points_balance=0,
    )
    dumped = _to_jsonable(user)
    assert dumped["email"] == "a@b.c"
    blob = _to_jsonable(b"hello")
    assert blob["encoding"] == "base64"
    assert base64.b64decode(blob["data"]) == b"hello"
    assert _to_jsonable(None) is None
    assert _to_jsonable({"x": 1}) == {"x": 1}


def test_client_holder_ensure_reuses_same_url():
    holder = ClientHolder()
    c1 = holder.ensure(base_url="http://localhost:1")
    c2 = holder.ensure(base_url="http://localhost:1")
    assert c1 is c2
    c3 = holder.ensure(base_url="http://localhost:2")
    assert c3 is not c1


def test_default_api_base_url_http_vs_stdio(monkeypatch):
    from qr_chores_client.mcp_server import _default_api_base_url

    monkeypatch.delenv("QR_CHORES_BASE_URL", raising=False)
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    assert _default_api_base_url() == "http://127.0.0.1:8000"
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    assert _default_api_base_url() == "http://127.0.0.1:8765"


@pytest.mark.asyncio
async def test_client_holder_ensure_logged_in_with_env(monkeypatch):
    holder = ClientHolder()
    mock_client = AsyncMock()
    mock_client.access_token = None
    mock_client.base_url = "http://test"
    mock_client.login = AsyncMock(return_value=MagicMock())

    with patch.object(holder, "ensure", return_value=mock_client):
        monkeypatch.setenv("QR_CHORES_EMAIL", "parent@example.com")
        monkeypatch.setenv("QR_CHORES_PASSWORD", "parent-pass")
        result = await holder.ensure_logged_in()
        mock_client.login.assert_awaited_once_with("parent@example.com", "parent-pass")
        assert result is mock_client


@pytest.mark.asyncio
async def test_client_holder_skips_login_if_token_present():
    holder = ClientHolder()
    mock_client = AsyncMock()
    mock_client.access_token = "already"
    mock_client.login = AsyncMock()
    with patch.object(holder, "ensure", return_value=mock_client):
        await holder.ensure_logged_in()
        mock_client.login.assert_not_awaited()


async def _tool_fn(name: str):
    tool = await mcp_server.mcp.get_tool(name)
    return tool.fn


@pytest.mark.asyncio
async def test_mcp_tools_parent_and_child_against_mock():
    """Drive every MCP tool against mock-api via ASGI client injected into holder."""
    from qr_chores_mock_api.app import app, reset_state

    reset_state()
    transport = ASGITransport(app=app)
    client = QrChoresClient("http://test", transport=transport)
    holder = mcp_server._holder
    old = holder.client
    holder.client = client
    try:
        login = await _tool_fn("login")
        tok = await login(email=PARENT_EMAIL, password=PARENT_PASSWORD)
        assert tok["access_token"] == "parent-token"
        assert tok["user"]["role"] == "parent"

        me = await (await _tool_fn("get_me"))()
        assert me["email"] == PARENT_EMAIL

        today = await (await _tool_fn("get_today"))()
        assert "board" in today

        history = await (await _tool_fn("get_history"))(limit=10)
        assert history["limit"] == 10

        days = await (await _tool_fn("get_history_days"))()
        assert days["days"][0]["done"] == 1

        chores = await (await _tool_fn("list_chores"))(include_inactive=True)
        assert len(chores["chores"]) >= 3

        created = await (await _tool_fn("create_chore"))(
            title="MCP chore",
            description="from test",
            due_time="17:00:00",
            schedule_days="0123456",
            photo_policy="none",
            base_points=3,
        )
        cid = created["id"]

        got = await (await _tool_fn("get_chore"))(chore_id=cid)
        assert got["title"] == "MCP chore"

        updated = await (await _tool_fn("update_chore"))(
            chore_id=cid,
            title="MCP chore 2",
            clear_description=True,
        )
        assert updated["title"] == "MCP chore 2"

        qr = await (await _tool_fn("get_qr_info"))(chore_id=cid)
        assert qr["chore_id"] == cid
        png = await (await _tool_fn("get_qr_png"))(chore_id=cid)
        assert png["encoding"] == "base64"

        await (await _tool_fn("deactivate_chore"))(chore_id=cid)
        await (await _tool_fn("activate_chore"))(chore_id=cid)

        rewards = await (await _tool_fn("get_rewards"))()
        assert "bonuses" in rewards

        bonuses = await (await _tool_fn("update_bonuses"))(
            early_bonus_points=4,
            on_time_bonus_points=1,
            late_bonus_points=0,
        )
        assert bonuses["early_bonus_points"] == 4

        ach = await (await _tool_fn("create_achievement"))(
            title="MCP ach",
            criteria_type="total_completions",
            threshold=2,
            points_reward=5,
        )
        aid = ach["id"]
        await (await _tool_fn("update_achievement"))(achievement_id=aid, title="MCP ach 2")
        toggled = await (await _tool_fn("toggle_achievement"))(achievement_id=aid)
        assert toggled["is_active"] is False

        photo = await (await _tool_fn("get_photo"))(completion_id=1)
        assert photo["encoding"] == "base64"

        deleted = await (await _tool_fn("delete_chore"))(chore_id=cid)
        assert deleted["deleted"] is True

        # Switch to child
        await login(email=CHILD_EMAIL, password=CHILD_PASSWORD)
        home = await (await _tool_fn("get_home"))()
        assert "board" in home

        conf = await (await _tool_fn("get_confirm"))(qr_token="qr-active-1")
        assert conf["chore"]["qr_token"] == "qr-active-1"

        # complete already done
        done = await (await _tool_fn("complete_chore"))(qr_token="qr-active-1")
        assert done["already_done"] is True

        # complete with photo base64
        b64 = base64.b64encode(TINY_PNG).decode("ascii")
        complete = await (await _tool_fn("complete_chore"))(
            qr_token="qr-photo-required",
            photo_base64=b64,
            photo_filename="bed.png",
        )
        assert complete["already_done"] is False

        achs = await (await _tool_fn("get_achievements"))()
        assert "achievements" in achs

        logged_out = await (await _tool_fn("logout"))()
        assert logged_out["status"] == "logged_out"
    finally:
        await client.aclose()
        holder.client = old
        reset_state()


@pytest.mark.asyncio
async def test_lifespan_auto_login_and_cleanup(monkeypatch):

    from qr_chores_mock_api.app import app, reset_state

    reset_state()
    transport = ASGITransport(app=app)
    client = QrChoresClient("http://test", transport=transport)

    holder = mcp_server._holder
    old = holder.client

    def ensure_side_effect(base_url=None, email=None, password=None):
        holder.client = client
        return client

    monkeypatch.setenv("QR_CHORES_EMAIL", PARENT_EMAIL)
    monkeypatch.setenv("QR_CHORES_PASSWORD", PARENT_PASSWORD)
    monkeypatch.setattr(holder, "ensure", ensure_side_effect)

    server = create_mcp_server()
    # FastMCP lifespan is on the server
    lifespan = server._lifespan
    try:
        if lifespan is not None:
            async with lifespan(server):
                assert holder.client is not None
                assert holder.client.access_token == "parent-token"
        # after exit client closed/cleared by lifespan on that server's holder —
        # note: lifespan closes _holder.client; we already swapped in our client
    finally:
        if holder.client is not None and holder.client is not client:
            await holder.client.aclose()
        if not client._client.is_closed:
            await client.aclose()
        holder.client = old
        reset_state()


def test_main_entry():
    with patch("qr_chores_client.mcp_server.run") as run_mock:
        from qr_chores_client.__main__ import main

        main()
        run_mock.assert_called_once()


def test_run_calls_mcp_run_stdio(monkeypatch):
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    with patch.object(mcp_server.mcp, "run") as run_mock:
        mcp_server.run()
        run_mock.assert_called_once_with()


def test_run_http_transport_from_env(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv("MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("MCP_PORT", "8001")
    monkeypatch.setenv("MCP_PATH", "/mcp")
    monkeypatch.setenv("MCP_STATELESS_HTTP", "1")
    with patch.object(mcp_server.mcp, "run") as run_mock:
        mcp_server.run()
        run_mock.assert_called_once_with(
            transport="http",
            host="127.0.0.1",
            port=8001,
            path="/mcp",
            show_banner=False,
            stateless_http=True,
            host_origin_protection=False,
        )


def test_run_http_stateless_off(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("MCP_STATELESS_HTTP", "0")
    with patch.object(mcp_server.mcp, "run") as run_mock:
        mcp_server.run()
        kwargs = run_mock.call_args.kwargs
        assert kwargs["transport"] == "streamable-http"
        assert kwargs["stateless_http"] is False


def test_parse_syslog_address():
    from qr_chores_client.mcp_server import _parse_syslog_address

    assert _parse_syslog_address("") is None
    assert _parse_syslog_address("logs.example") == ("logs.example", 514)
    assert _parse_syslog_address("logs.example:1514") == ("logs.example", 1514)
    assert _parse_syslog_address("udp://logs.example:514") == ("logs.example", 514)


def test_configure_mcp_logging_console(monkeypatch):
    from qr_chores_client.mcp_server import configure_mcp_logging

    monkeypatch.delenv("SYSLOG_SERVER", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    configure_mcp_logging()
    # idempotent second call
    configure_mcp_logging()


def test_env_helper():
    from qr_chores_client.mcp_server import _env

    assert _env("DEFINITELY_MISSING_QR_CHORES_VAR_XYZ", "d") == "d"
    os.environ["QR_CHORES_TEST_ONLY"] = "v"
    try:
        assert _env("QR_CHORES_TEST_ONLY") == "v"
        assert _env("QR_CHORES_TEST_ONLY", "d") == "v"
    finally:
        del os.environ["QR_CHORES_TEST_ONLY"]
    # empty string treated as missing
    os.environ["QR_CHORES_TEST_ONLY"] = ""
    try:
        assert _env("QR_CHORES_TEST_ONLY", "fallback") == "fallback"
    finally:
        del os.environ["QR_CHORES_TEST_ONLY"]


@pytest.mark.asyncio
async def test_oauth_well_known_metadata():
    from starlette.testclient import TestClient

    from qr_chores_client.mcp_server import DatabaseOAuthProvider, FastMCP

    auth = DatabaseOAuthProvider(base_url="http://127.0.0.1:8001")
    server = FastMCP("test-oauth", auth=auth)
    app = server.http_app(transport="http", path="/mcp", stateless_http=True)

    with TestClient(app) as client:
        res_auth = client.get("/.well-known/oauth-authorization-server")
        assert res_auth.status_code == 200
        auth_data = res_auth.json()
        assert "authorization_endpoint" in auth_data
        assert "token_endpoint" in auth_data

        res_prot = client.get("/.well-known/oauth-protected-resource/mcp")
        assert res_prot.status_code == 200
        assert res_prot.json()["resource"] == "http://127.0.0.1:8001/mcp"

        res_root = client.get("/.well-known/oauth-protected-resource")
        assert res_root.status_code == 200
        assert res_root.json()["resource"] == "http://127.0.0.1:8001/mcp"


@pytest.mark.asyncio
async def test_oauth_client_registration_and_token_flow():
    import hashlib
    import secrets

    from starlette.testclient import TestClient

    from qr_chores_client.mcp_server import DatabaseOAuthProvider, FastMCP

    auth = DatabaseOAuthProvider(base_url="http://127.0.0.1:8001")
    server = FastMCP("test-oauth-flow", auth=auth)

    @server.tool
    async def echo_auth(ctx: Any = None) -> dict:
        req = (
            getattr(ctx.request_context, "request", None)
            if ctx and hasattr(ctx, "request_context")
            else None
        )
        auth_h = req.headers.get("authorization") if req else None
        return {"auth": auth_h}

    app = server.http_app(transport="http", path="/mcp", stateless_http=True)

    with TestClient(app) as client:
        # Dynamic client registration under /mcp/register
        reg = client.post(
            "/mcp/register",
            json={"client_name": "Test App", "redirect_uris": ["http://localhost/callback"]},
        )
        assert reg.status_code == 201
        cinfo = reg.json()
        assert "client_id" in cinfo

        # Authorize request with PKCE S256 under /mcp/authorize
        code_verifier = "test_verifier_" + secrets.token_hex(16)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        auth_res = client.get(
            f"/mcp/authorize?response_type=code&client_id={cinfo['client_id']}&redirect_uri=http://localhost/callback&state=state123&code_challenge={code_challenge}&code_challenge_method=S256",
            follow_redirects=False,
        )
        assert auth_res.status_code == 302
        loc = auth_res.headers["location"]
        assert "code=" in loc
        code = loc.split("code=")[1].split("&")[0]

        # Token exchange under /mcp/token
        tok_res = client.post(
            "/mcp/token",
            data={
                "grant_type": "authorization_code",
                "client_id": cinfo["client_id"],
                "client_secret": cinfo.get("client_secret", ""),
                "code": code,
                "redirect_uri": "http://localhost/callback",
                "code_verifier": code_verifier,
            },
            auth=(cinfo["client_id"], cinfo.get("client_secret", "")),
        )
        assert tok_res.status_code == 200
        tokens = tok_res.json()
        assert "access_token" in tokens
        access_tok = tokens["access_token"]

        # Call MCP tool with Bearer header
        mcp_res = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "echo_auth", "arguments": {}},
            },
            headers={
                "Authorization": f"Bearer {access_tok}",
                "Accept": "application/json, text/event-stream",
            },
        )
        assert mcp_res.status_code == 200


@pytest.mark.asyncio
async def test_oauth_provider_revocation_and_auto_client():
    from qr_chores_client.mcp_server import DatabaseOAuthProvider

    auth = DatabaseOAuthProvider(base_url="http://127.0.0.1:8001")
    # Auto-register unknown client_id
    cinfo = await auth.get_client("unknown-chatgpt-id")
    assert cinfo is not None
    assert cinfo.client_id == "unknown-chatgpt-id"

    # Revoke token
    await auth.revoke_token("dummy-token")
