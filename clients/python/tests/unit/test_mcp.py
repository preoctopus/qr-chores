"""MCP server registration and tool call smoke tests."""

from __future__ import annotations

import base64
import os
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


def test_run_calls_mcp_run():
    with patch.object(mcp_server.mcp, "run") as run_mock:
        mcp_server.run()
        run_mock.assert_called_once()


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
