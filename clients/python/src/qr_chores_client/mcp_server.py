"""FastMCP server wrapping QrChoresClient as tools."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel

from qr_chores_client.client import QrChoresClient
from qr_chores_client.models import (
    AchievementCreate,
    AchievementUpdate,
    ChoreCreate,
    ChoreUpdate,
)

try:
    from fastmcp import FastMCP
except ImportError:  # pragma: no cover
    FastMCP = None  # type: ignore[misc, assignment]


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return json.loads(value.model_dump_json())
    if isinstance(value, (bytes, bytearray)):
        return {
            "encoding": "base64",
            "content_type": "application/octet-stream",
            "data": base64.b64encode(bytes(value)).decode("ascii"),
            "size": len(value),
        }
    if value is None:
        return None
    return value


def _env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val


def _default_api_base_url() -> str:
    """API origin when no base_url / QR_CHORES_BASE_URL is set.

    HTTP MCP (Docker: co-located uvicorn on :8000) defaults to loopback :8000.
    Stdio / local CLI-style runs default to the local app port :8765.
    """
    transport = (_env("MCP_TRANSPORT", "stdio") or "stdio").strip().lower()
    if transport in {"http", "streamable-http", "sse"}:
        return "http://127.0.0.1:8000"
    return "http://127.0.0.1:8765"


class ClientHolder:
    """Holds a shared async client for MCP tool calls."""

    def __init__(self) -> None:
        self.client: QrChoresClient | None = None

    def ensure(
        self,
        base_url: str | None = None,
        email: str | None = None,
        password: str | None = None,
    ) -> QrChoresClient:
        # Keep an already-injected client unless the caller overrides base_url.
        if self.client is not None and base_url is None:
            return self.client
        url = (base_url or _env("QR_CHORES_BASE_URL") or _default_api_base_url()).rstrip("/")
        if self.client is None or self.client.base_url != url:
            self.client = QrChoresClient(url)
        return self.client

    async def ensure_logged_in(
        self,
        base_url: str | None = None,
        email: str | None = None,
        password: str | None = None,
    ) -> QrChoresClient:
        client = self.ensure(base_url=base_url)
        if client.access_token:
            return client
        em = email or _env("QR_CHORES_EMAIL")
        pw = password or _env("QR_CHORES_PASSWORD")
        if em and pw:
            await client.login(em, pw)
        return client


_holder = ClientHolder()


def create_mcp_server() -> Any:
    """Build and return a FastMCP instance with all API tools registered."""
    if FastMCP is None:  # pragma: no cover
        raise ImportError("fastmcp is required to run the MCP server")

    @asynccontextmanager
    async def lifespan(server: Any) -> AsyncIterator[None]:
        del server
        # Auto-login if env credentials present
        em = _env("QR_CHORES_EMAIL")
        pw = _env("QR_CHORES_PASSWORD")
        if em and pw:
            await _holder.ensure_logged_in()
        try:
            yield
        finally:
            if _holder.client is not None:
                await _holder.client.aclose()
                _holder.client = None

    mcp = FastMCP(
        "qr-chores",
        instructions=(
            "Tools for the QR Chores family chore API (/api/v1). "
            "Set QR_CHORES_BASE_URL, QR_CHORES_EMAIL, QR_CHORES_PASSWORD for auto-login, "
            "or call the login tool with credentials."
        ),
        lifespan=lifespan,
    )

    @mcp.tool
    async def login(
        email: str,
        password: str,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        """Log in and store the access token for subsequent tools."""
        client = _holder.ensure(base_url=base_url)
        token = await client.login(email, password)
        return _to_jsonable(token)

    @mcp.tool
    async def logout() -> dict[str, str]:
        """Log out and clear the stored access token."""
        client = _holder.ensure()
        await client.logout()
        return {"status": "logged_out"}

    @mcp.tool
    async def get_me() -> dict[str, Any]:
        """Return the currently authenticated user."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.get_me())

    @mcp.tool
    async def get_home() -> dict[str, Any]:
        """Child home board for today (requires child role)."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.get_home())

    @mcp.tool
    async def get_confirm(qr_token: str) -> dict[str, Any]:
        """Confirm payload for a chore QR token (child)."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.get_confirm(qr_token))

    @mcp.tool
    async def complete_chore(
        qr_token: str,
        photo_base64: str | None = None,
        photo_filename: str = "photo.jpg",
    ) -> dict[str, Any]:
        """Complete a chore by QR token. Optionally attach a base64-encoded photo."""
        client = await _holder.ensure_logged_in()
        photo: bytes | None = None
        if photo_base64:
            photo = base64.b64decode(photo_base64)
        return _to_jsonable(
            await client.complete_chore(
                qr_token,
                photo=photo,
                photo_filename=photo_filename,
            )
        )

    @mcp.tool
    async def get_achievements() -> dict[str, Any]:
        """Child achievement progress."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.get_achievements())

    @mcp.tool
    async def get_today() -> dict[str, Any]:
        """Parent today board."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.get_today())

    @mcp.tool
    async def get_history(limit: int = 50) -> dict[str, Any]:
        """Parent completion history."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.get_history(limit=limit))

    @mcp.tool
    async def list_chores(include_inactive: bool = True) -> dict[str, Any]:
        """List chores (parent)."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.list_chores(include_inactive=include_inactive))

    @mcp.tool
    async def create_chore(
        title: str,
        description: str | None = None,
        due_time: str = "20:00:00",
        schedule_days: str = "0123456",
        photo_policy: str = "none",
        base_points: int = 10,
    ) -> dict[str, Any]:
        """Create a chore (parent)."""
        client = await _holder.ensure_logged_in()
        chore = ChoreCreate(
            title=title,
            description=description,
            due_time=due_time,
            schedule_days=schedule_days,
            photo_policy=photo_policy,
            base_points=base_points,
        )
        return _to_jsonable(await client.create_chore(chore))

    @mcp.tool
    async def get_chore(chore_id: int) -> dict[str, Any]:
        """Get chore by id (parent)."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.get_chore(chore_id))

    @mcp.tool
    async def update_chore(
        chore_id: int,
        title: str | None = None,
        description: str | None = None,
        due_time: str | None = None,
        schedule_days: str | None = None,
        photo_policy: str | None = None,
        base_points: int | None = None,
        clear_description: bool = False,
    ) -> dict[str, Any]:
        """Partial update of a chore (parent)."""
        client = await _holder.ensure_logged_in()
        update = ChoreUpdate(
            title=title,
            description=description,
            due_time=due_time,
            schedule_days=schedule_days,
            photo_policy=photo_policy,
            base_points=base_points,
            clear_description=clear_description,
        )
        return _to_jsonable(await client.update_chore(chore_id, update))

    @mcp.tool
    async def delete_chore(chore_id: int) -> dict[str, Any]:
        """Hard-delete a chore (parent)."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.delete_chore(chore_id))

    @mcp.tool
    async def activate_chore(chore_id: int) -> dict[str, Any]:
        """Activate a chore (parent)."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.activate_chore(chore_id))

    @mcp.tool
    async def deactivate_chore(chore_id: int) -> dict[str, Any]:
        """Deactivate a chore (parent)."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.deactivate_chore(chore_id))

    @mcp.tool
    async def get_qr_info(chore_id: int) -> dict[str, Any]:
        """QR metadata for a chore (parent)."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.get_qr_info(chore_id))

    @mcp.tool
    async def get_qr_png(chore_id: int) -> dict[str, Any]:
        """QR PNG bytes as base64 (parent)."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.get_qr_png(chore_id))

    @mcp.tool
    async def get_rewards() -> dict[str, Any]:
        """Timing bonuses and achievements (parent)."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.get_rewards())

    @mcp.tool
    async def update_bonuses(
        early_bonus_points: int,
        on_time_bonus_points: int,
        late_bonus_points: int,
    ) -> dict[str, Any]:
        """Update timing bonus points (parent)."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(
            await client.update_bonuses(
                early_bonus_points=early_bonus_points,
                on_time_bonus_points=on_time_bonus_points,
                late_bonus_points=late_bonus_points,
            )
        )

    @mcp.tool
    async def create_achievement(
        title: str,
        criteria_type: str,
        description: str = "",
        icon_key: str = "star",
        threshold: int = 1,
        points_reward: int = 0,
    ) -> dict[str, Any]:
        """Create an achievement (parent)."""
        client = await _holder.ensure_logged_in()
        ach = AchievementCreate(
            title=title,
            description=description,
            icon_key=icon_key,
            criteria_type=criteria_type,
            threshold=threshold,
            points_reward=points_reward,
        )
        return _to_jsonable(await client.create_achievement(ach))

    @mcp.tool
    async def update_achievement(
        achievement_id: int,
        title: str | None = None,
        description: str | None = None,
        icon_key: str | None = None,
        criteria_type: str | None = None,
        threshold: int | None = None,
        points_reward: int | None = None,
    ) -> dict[str, Any]:
        """Update an achievement (parent)."""
        client = await _holder.ensure_logged_in()
        update = AchievementUpdate(
            title=title,
            description=description,
            icon_key=icon_key,
            criteria_type=criteria_type,
            threshold=threshold,
            points_reward=points_reward,
        )
        return _to_jsonable(await client.update_achievement(achievement_id, update))

    @mcp.tool
    async def toggle_achievement(achievement_id: int) -> dict[str, Any]:
        """Toggle achievement is_active (parent)."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.toggle_achievement(achievement_id))

    @mcp.tool
    async def get_photo(completion_id: int) -> dict[str, Any]:
        """Fetch proof photo bytes as base64 (any authenticated user)."""
        client = await _holder.ensure_logged_in()
        return _to_jsonable(await client.get_photo(completion_id))

    return mcp


# Module-level server for `fastmcp run` / python -m
mcp = create_mcp_server()


def list_tool_names() -> list[str]:
    """Return registered tool names (for tests / discovery)."""
    # Prefer async list_tools when available (FastMCP 3.x)
    try:
        import asyncio

        async def _names() -> list[str]:
            tools = await mcp.list_tools()
            return sorted(t.name for t in tools)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_names())
    except Exception:
        pass
    # Fall back to known names from this module
    return sorted(
        [
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
        ]
    )


def run() -> None:
    """Run the MCP server.

    Defaults to **stdio** (local IDE / Claude Desktop). In Docker, set
    ``MCP_TRANSPORT=http`` (or ``streamable-http`` / ``sse``) to serve HTTP
    behind nginx at ``MCP_PATH`` (default ``/mcp``).

    Environment
    -----------
    MCP_TRANSPORT
        ``stdio`` (default), ``http``, ``streamable-http``, or ``sse``.
    MCP_HOST / MCP_PORT / MCP_PATH
        Bind address for HTTP transports (defaults ``127.0.0.1``, ``8001``, ``/mcp``).
    MCP_STATELESS_HTTP
        ``1`` (default when HTTP) enables stateless streamable HTTP — better behind
        reverse proxies / Cloud Run.
    QR_CHORES_EMAIL / QR_CHORES_PASSWORD
        Optional auto-login for tools (local / Docker secrets).
    """
    transport = (_env("MCP_TRANSPORT", "stdio") or "stdio").strip().lower()
    if transport in {"http", "streamable-http", "sse"}:
        host = _env("MCP_HOST", "127.0.0.1") or "127.0.0.1"
        port = int(_env("MCP_PORT", "8001") or "8001")
        path = _env("MCP_PATH", "/mcp") or "/mcp"
        # Default stateless for HTTP so reverse proxies / multi-instance work.
        stateless_raw = _env("MCP_STATELESS_HTTP", "1") or "1"
        stateless = stateless_raw.strip().lower() in {"1", "true", "yes", "on"}
        mcp.run(
            transport=transport,  # type: ignore[arg-type]
            host=host,
            port=port,
            path=path,
            show_banner=False,
            stateless_http=stateless,
            # Nginx forwards the public Host header; do not reject it.
            host_origin_protection=False,
        )
        return
    mcp.run()
