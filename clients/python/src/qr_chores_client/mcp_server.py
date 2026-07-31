"""FastMCP server wrapping QrChoresClient as tools with OAuth 2.1 support."""

from __future__ import annotations

import base64
import json
import logging
import logging.handlers
import os
import secrets
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from qr_chores_client.client import QrChoresClient
from qr_chores_client.models import (
    AchievementCreate,
    AchievementUpdate,
    ChoreCreate,
    ChoreUpdate,
)

logger = logging.getLogger("qr_chores_mcp")

try:
    from fastmcp import Context, FastMCP
    from fastmcp.server.auth.auth import AccessToken, ClientRegistrationOptions
    from fastmcp.server.auth.providers.in_memory import (
        DEFAULT_ACCESS_TOKEN_EXPIRY_SECONDS,
        DEFAULT_AUTH_CODE_EXPIRY_SECONDS,
        AuthorizationCode,
        AuthorizationParams,
        InMemoryOAuthProvider,
        RefreshToken,
        construct_redirect_uri,
    )
    from mcp.shared.auth import OAuthClientInformationFull
    from mcp.shared.auth import OAuthToken as OAuthTokenData
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route
except ImportError:  # pragma: no cover
    FastMCP = None  # type: ignore[misc, assignment]
    Context = None  # type: ignore[misc, assignment]


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


def _get_db_and_store():
    try:
        from qr_chores.db import SessionLocal
        from qr_chores.services import oauth_store

        return SessionLocal, oauth_store
    except Exception:
        return None, None


class DatabaseOAuthProvider(InMemoryOAuthProvider if FastMCP else object):  # type: ignore[misc]
    """Postgres / SQLite DB-backed OAuth 2.1 provider for FastMCP."""

    def __init__(self, base_url: str, api_base_url: str | None = None) -> None:
        super().__init__(
            base_url=base_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
        )
        self.api_base_url = (api_base_url or _default_api_base_url()).rstrip("/")

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        if not client_id:
            return None
        session_factory, store = _get_db_and_store()
        if session_factory and store:
            async with session_factory() as session:
                db_client = await store.get_oauth_client(session, client_id)
                if db_client:
                    return OAuthClientInformationFull(
                        client_id=db_client.client_id,
                        client_secret=db_client.client_secret,
                        client_name=db_client.client_name,
                        redirect_uris=json.loads(db_client.redirect_uris_json),
                        grant_types=json.loads(db_client.grant_types_json),
                        response_types=json.loads(db_client.response_types_json),
                        token_endpoint_auth_method=db_client.token_endpoint_auth_method,
                    )
        if client_id in self.clients:
            return self.clients[client_id]
        auto_client = OAuthClientInformationFull(
            client_id=client_id,
            client_name=f"Client {client_id}",
            redirect_uris=[
                "https://chatgpt.com/aip/g-123/oauth/callback",
                "https://chat.openai.com/aip/g-123/oauth/callback",
                "http://localhost/callback",
            ],
            token_endpoint_auth_method="none",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        )
        await self.register_client(auto_client)
        return auto_client

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise ValueError("client_id is required")
        session_factory, store = _get_db_and_store()
        if session_factory and store:
            async with session_factory() as session:
                await store.save_oauth_client(
                    session=session,
                    client_id=client_info.client_id,
                    client_secret=client_info.client_secret,
                    client_name=client_info.client_name or "",
                    redirect_uris=list(client_info.redirect_uris or []),
                    grant_types=list(client_info.grant_types or []),
                    response_types=list(client_info.response_types or []),
                    token_endpoint_auth_method=client_info.token_endpoint_auth_method or "none",
                )
        self.clients[client_info.client_id] = client_info

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        auth_code_value = f"auth_code_{secrets.token_hex(16)}"
        expires_at = datetime.now(UTC) + timedelta(seconds=DEFAULT_AUTH_CODE_EXPIRY_SECONDS)
        user_id = getattr(params, "user_id", 1)

        scopes_list = list(params.scopes or [])
        auth_code_obj = AuthorizationCode(
            code=auth_code_value,
            client_id=client.client_id,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            scopes=scopes_list,
            expires_at=int(expires_at.timestamp()),
            code_challenge=params.code_challenge,
        )
        self.auth_codes[auth_code_value] = auth_code_obj

        session_factory, store = _get_db_and_store()
        if session_factory and store:
            async with session_factory() as session:
                await store.create_oauth_code(
                    session=session,
                    code=auth_code_value,
                    client_id=client.client_id,
                    user_id=user_id,
                    redirect_uri=str(params.redirect_uri),
                    code_challenge=params.code_challenge or "",
                    code_challenge_method="S256",
                    scopes=scopes_list,
                    expires_at=expires_at,
                )

        return construct_redirect_uri(
            str(params.redirect_uri), code=auth_code_value, state=params.state
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        session_factory, store = _get_db_and_store()
        if session_factory and store:
            async with session_factory() as session:
                db_code = await store.get_oauth_code(session, authorization_code)
                if db_code:
                    if db_code.client_id != client.client_id:
                        return None
                    exp_timestamp = int(db_code.expires_at.timestamp())
                    return AuthorizationCode(
                        code=db_code.code,
                        client_id=db_code.client_id,
                        redirect_uri=db_code.redirect_uri,
                        redirect_uri_provided_explicitly=True,
                        scopes=json.loads(db_code.scopes_json),
                        expires_at=exp_timestamp,
                        code_challenge=db_code.code_challenge,
                    )
        return await super().load_authorization_code(client, authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthTokenData:
        user_id = 1
        session_factory, store = _get_db_and_store()
        if session_factory and store:
            async with session_factory() as session:
                db_code = await store.get_oauth_code(session, authorization_code.code)
                if db_code:
                    user_id = db_code.user_id
                await store.delete_oauth_code(session, authorization_code.code)

        if authorization_code.code in self.auth_codes:
            del self.auth_codes[authorization_code.code]

        access_token_val = f"oauth_access_{secrets.token_hex(32)}"
        refresh_token_val = f"oauth_refresh_{secrets.token_hex(32)}"
        expires_at_dt = datetime.now(UTC) + timedelta(seconds=DEFAULT_ACCESS_TOKEN_EXPIRY_SECONDS)
        expires_at_ts = int(expires_at_dt.timestamp())

        tok_obj = AccessToken(
            token=access_token_val,
            client_id=client.client_id,
            scopes=authorization_code.scopes or [],
            expires_at=expires_at_ts,
        )
        self.access_tokens[access_token_val] = tok_obj
        if refresh_token_val:
            ref_obj = RefreshToken(
                token=refresh_token_val,
                client_id=client.client_id,
                scopes=authorization_code.scopes or [],
                expires_at=expires_at_ts,
            )
            self.refresh_tokens[refresh_token_val] = ref_obj

        if session_factory and store:
            async with session_factory() as session:
                await store.create_oauth_token(
                    session=session,
                    access_token=access_token_val,
                    refresh_token=refresh_token_val,
                    client_id=client.client_id,
                    user_id=user_id,
                    scopes=authorization_code.scopes or [],
                    expires_at=expires_at_dt,
                )

        return OAuthTokenData(
            access_token=access_token_val,
            token_type="Bearer",
            expires_in=DEFAULT_ACCESS_TOKEN_EXPIRY_SECONDS,
            refresh_token=refresh_token_val,
            scope=" ".join(authorization_code.scopes or []),
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        session_factory, store = _get_db_and_store()
        if session_factory and store:
            async with session_factory() as session:
                db_token = await store.get_oauth_token(session, token)
                if not db_token:
                    return None
                exp_ts = int(db_token.expires_at.timestamp())
                if time.time() > exp_ts:
                    return None
                return AccessToken(
                    token=db_token.access_token,
                    client_id=db_token.client_id,
                    scopes=json.loads(db_token.scopes_json),
                    expires_at=exp_ts,
                )
        return await super().load_access_token(token)

    async def verify_token(self, token: str) -> AccessToken | None:
        return await self.load_access_token(token)

    async def revoke_token(self, token: Any) -> None:
        tok_str = getattr(token, "token", str(token))
        session_factory, store = _get_db_and_store()
        if session_factory and store:
            async with session_factory() as session:
                await store.revoke_oauth_token(session, tok_str)

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        base_routes = super().get_routes(mcp_path)
        prefix = (mcp_path or "/mcp").rstrip("/")
        issuer = str(self.issuer_url or self.base_url).rstrip("/")

        new_routes: list[Route] = []
        for r in base_routes:
            if isinstance(r, Route):
                new_routes.append(r)
                if r.path in ("/authorize", "/token", "/register"):
                    new_routes.append(
                        Route(
                            path=f"{prefix}{r.path}",
                            endpoint=r.endpoint,
                            methods=r.methods,
                        )
                    )

        auth_meta = {
            "issuer": str(self.issuer_url or self.base_url),
            "authorization_endpoint": f"{issuer}{prefix}/authorize",
            "token_endpoint": f"{issuer}{prefix}/token",
            "registration_endpoint": f"{issuer}{prefix}/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": [
                "none",
                "client_secret_post",
                "client_secret_basic",
            ],
            "code_challenge_methods_supported": ["S256"],
        }

        resource_meta = {
            "resource": str(self._get_resource_url(mcp_path)),
            "authorization_servers": [str(self.issuer_url or self.base_url)],
            "scopes_supported": [],
            "bearer_methods_supported": ["header"],
        }

        async def _custom_auth_meta(req: Request) -> JSONResponse:
            return JSONResponse(auth_meta)

        async def _custom_res_meta(req: Request) -> JSONResponse:
            return JSONResponse(resource_meta)

        final_routes: list[Route] = [
            Route(
                "/.well-known/oauth-protected-resource", endpoint=_custom_res_meta, methods=["GET"]
            ),
        ]
        for r in new_routes:
            if isinstance(r, Route) and r.path == "/.well-known/oauth-authorization-server":
                final_routes.append(
                    Route(
                        "/.well-known/oauth-authorization-server",
                        endpoint=_custom_auth_meta,
                        methods=["GET"],
                    )
                )
                final_routes.append(
                    Route(
                        f"{prefix}/.well-known/oauth-authorization-server",
                        endpoint=_custom_auth_meta,
                        methods=["GET"],
                    )
                )
                final_routes.append(
                    Route(
                        "/.well-known/openid-configuration",
                        endpoint=_custom_auth_meta,
                        methods=["GET"],
                    )
                )
                final_routes.append(
                    Route(
                        f"{prefix}/.well-known/openid-configuration",
                        endpoint=_custom_auth_meta,
                        methods=["GET"],
                    )
                )
            else:
                final_routes.append(r)

        return final_routes


class ClientHolder:
    """Holds a shared async client for MCP tool calls."""

    def __init__(self) -> None:
        self.client: QrChoresClient | None = None

    def ensure(
        self,
        base_url: str | None = None,
        email: str | None = None,
        password: str | None = None,
        access_token: str | None = None,
    ) -> QrChoresClient:
        # Keep an already-injected client unless the caller overrides base_url.
        if self.client is not None and base_url is None:
            if access_token:
                self.client.access_token = access_token
            return self.client
        url = (base_url or _env("QR_CHORES_BASE_URL") or _default_api_base_url()).rstrip("/")
        if self.client is None or self.client.base_url != url:
            self.client = QrChoresClient(url, access_token=access_token)
        elif access_token:
            self.client.access_token = access_token
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

    async def get_client_for_request(
        self,
        ctx: Any | None = None,
        base_url: str | None = None,
    ) -> QrChoresClient:
        token: str | None = None
        if ctx and hasattr(ctx, "request_context") and ctx.request_context:
            req = getattr(ctx.request_context, "request", None)
            if req and hasattr(req, "headers"):
                auth_h = req.headers.get("authorization") or req.headers.get("Authorization")
                if auth_h and auth_h.lower().startswith("bearer "):
                    token = auth_h[7:].strip()

        if token:
            return self.ensure(base_url=base_url, access_token=token)

        return await self.ensure_logged_in(base_url=base_url)


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

    auth_provider = None
    oauth_enabled = _env("MCP_OAUTH_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
    transport = (_env("MCP_TRANSPORT", "stdio") or "stdio").strip().lower()
    if oauth_enabled and transport in {"http", "streamable-http", "sse"}:
        host = _env("MCP_HOST", "127.0.0.1") or "127.0.0.1"
        port = int(_env("MCP_PORT", "8001") or "8001")
        base_url = _env("MCP_PUBLIC_URL") or _env("BASE_URL") or f"http://{host}:{port}"
        auth_provider = DatabaseOAuthProvider(base_url=base_url)

    mcp = FastMCP(
        "qr-chores",
        instructions=(
            "Tools for the QR Chores family chore API (/api/v1). "
            "Supports OAuth 2.1 for ChatGPT / remote connectors, or set QR_CHORES_EMAIL "
            "and QR_CHORES_PASSWORD for auto-login."
        ),
        lifespan=lifespan,
        auth=auth_provider,
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
    async def get_me(ctx: Any = None) -> dict[str, Any]:
        """Return the currently authenticated user."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.get_me())

    @mcp.tool
    async def get_home(ctx: Any = None) -> dict[str, Any]:
        """Child home board for today (requires child role)."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.get_home())

    @mcp.tool
    async def get_confirm(qr_token: str, ctx: Any = None) -> dict[str, Any]:
        """Confirm payload for a chore QR token (child)."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.get_confirm(qr_token))

    @mcp.tool
    async def complete_chore(
        qr_token: str,
        photo_base64: str | None = None,
        photo_filename: str = "photo.jpg",
        notes: str | None = None,
        ctx: Any = None,
    ) -> dict[str, Any]:
        """Complete a chore by QR token. Optionally attach a base64-encoded photo and/or note for parents."""
        client = await _holder.get_client_for_request(ctx)
        photo: bytes | None = None
        if photo_base64:
            photo = base64.b64decode(photo_base64)
        return _to_jsonable(
            await client.complete_chore(
                qr_token,
                photo=photo,
                photo_filename=photo_filename,
                notes=notes,
            )
        )

    @mcp.tool
    async def get_achievements(ctx: Any = None) -> dict[str, Any]:
        """Child achievement progress."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.get_achievements())

    @mcp.tool
    async def get_today(ctx: Any = None) -> dict[str, Any]:
        """Parent today board."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.get_today())

    @mcp.tool
    async def get_history(
        child_id: int | None = None,
        chore_id: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        timing: str | None = None,
        page: int = 1,
        limit: int = 50,
        ctx: Any = None,
    ) -> dict[str, Any]:
        """Parent completion history with optional filters (child_id, chore_id, start_date, end_date, timing), pagination, and stats."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(
            await client.get_history(
                child_id=child_id,
                chore_id=chore_id,
                start_date=start_date,
                end_date=end_date,
                timing=timing,
                page=page,
                limit=limit,
            )
        )

    @mcp.tool
    async def undo_chore_completion(completion_id: int, ctx: Any = None) -> dict[str, Any]:
        """Undo a chore completion for a parent's child (parent role required). Reverts banked points and deletes proof photo if present."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.undo_completion(completion_id))

    @mcp.tool
    async def list_chores(include_inactive: bool = True, ctx: Any = None) -> dict[str, Any]:
        """List chores (parent)."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.list_chores(include_inactive=include_inactive))

    @mcp.tool
    async def create_chore(
        title: str,
        description: str | None = None,
        due_time: str = "20:00:00",
        schedule_days: str = "0123456",
        photo_policy: str = "none",
        base_points: int = 10,
        early_bonus_enabled: bool = True,
        ctx: Any = None,
    ) -> dict[str, Any]:
        """Create a chore (parent)."""
        client = await _holder.get_client_for_request(ctx)
        chore = ChoreCreate(
            title=title,
            description=description,
            due_time=due_time,
            schedule_days=schedule_days,
            photo_policy=photo_policy,
            base_points=base_points,
            early_bonus_enabled=early_bonus_enabled,
        )
        return _to_jsonable(await client.create_chore(chore))

    @mcp.tool
    async def get_chore(chore_id: int, ctx: Any = None) -> dict[str, Any]:
        """Get chore by id (parent)."""
        client = await _holder.get_client_for_request(ctx)
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
        early_bonus_enabled: bool | None = None,
        clear_description: bool = False,
        ctx: Any = None,
    ) -> dict[str, Any]:
        """Partial update of a chore (parent)."""
        client = await _holder.get_client_for_request(ctx)
        update = ChoreUpdate(
            title=title,
            description=description,
            due_time=due_time,
            schedule_days=schedule_days,
            photo_policy=photo_policy,
            base_points=base_points,
            early_bonus_enabled=early_bonus_enabled,
            clear_description=clear_description,
        )
        return _to_jsonable(await client.update_chore(chore_id, update))

    @mcp.tool
    async def delete_chore(chore_id: int, ctx: Any = None) -> dict[str, Any]:
        """Hard-delete a chore (parent)."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.delete_chore(chore_id))

    @mcp.tool
    async def activate_chore(chore_id: int, ctx: Any = None) -> dict[str, Any]:
        """Activate a chore (parent)."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.activate_chore(chore_id))

    @mcp.tool
    async def deactivate_chore(chore_id: int, ctx: Any = None) -> dict[str, Any]:
        """Deactivate a chore (parent)."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.deactivate_chore(chore_id))

    @mcp.tool
    async def get_qr_info(chore_id: int, ctx: Any = None) -> dict[str, Any]:
        """QR metadata for a chore (parent)."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.get_qr_info(chore_id))

    @mcp.tool
    async def get_qr_png(chore_id: int, ctx: Any = None) -> dict[str, Any]:
        """QR PNG bytes as base64 (parent)."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.get_qr_png(chore_id))

    @mcp.tool
    async def get_rewards(ctx: Any = None) -> dict[str, Any]:
        """Timing bonuses and achievements (parent)."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.get_rewards())

    @mcp.tool
    async def update_bonuses(
        early_bonus_points: int,
        on_time_bonus_points: int,
        late_bonus_points: int,
        ctx: Any = None,
    ) -> dict[str, Any]:
        """Update timing bonus points (parent)."""
        client = await _holder.get_client_for_request(ctx)
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
        ctx: Any = None,
    ) -> dict[str, Any]:
        """Create an achievement (parent)."""
        client = await _holder.get_client_for_request(ctx)
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
        ctx: Any = None,
    ) -> dict[str, Any]:
        """Update an achievement (parent)."""
        client = await _holder.get_client_for_request(ctx)
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
    async def toggle_achievement(achievement_id: int, ctx: Any = None) -> dict[str, Any]:
        """Toggle achievement is_active (parent)."""
        client = await _holder.get_client_for_request(ctx)
        return _to_jsonable(await client.toggle_achievement(achievement_id))

    @mcp.tool
    async def get_photo(completion_id: int, ctx: Any = None) -> dict[str, Any]:
        """Fetch proof photo bytes as base64 (any authenticated user)."""
        client = await _holder.get_client_for_request(ctx)
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


def _parse_syslog_address(server: str) -> tuple[str, int] | None:
    raw = (server or "").strip()
    if not raw:
        return None
    for prefix in ("udp://", "tcp://", "syslog://"):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix) :]
            break
    if not raw:
        return None
    if raw.count(":") == 1:
        host, _, port_s = raw.partition(":")
        if not host or not port_s.isdigit():
            return None
        return host, int(port_s)
    return raw, 514


def configure_mcp_logging() -> None:
    """Console always; dual-write to SYSLOG_SERVER when set (same env as app/nginx)."""
    level_name = (_env("LOG_LEVEL", "INFO") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    # Avoid stacking handlers if run() is invoked more than once in tests.
    if not any(getattr(h, "_qr_chores_mcp", False) for h in root.handlers):
        root.setLevel(level)
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(level)
        console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        console._qr_chores_mcp = True  # type: ignore[attr-defined]
        root.addHandler(console)

        addr = _parse_syslog_address(_env("SYSLOG_SERVER", "") or "")
        if addr is not None:
            host, port = addr
            try:
                syslog = logging.handlers.SysLogHandler(
                    address=(host, port),
                    facility=logging.handlers.SysLogHandler.LOG_LOCAL0,
                )
                syslog.setLevel(level)
                syslog.setFormatter(
                    logging.Formatter(
                        "qr-chores-mcp[%(process)d]: %(levelname)s [%(name)s] %(message)s"
                    )
                )
                syslog._qr_chores_mcp = True  # type: ignore[attr-defined]
                root.addHandler(syslog)
                logger.info("Syslog handler enabled → %s:%s", host, port)
            except OSError as exc:
                logger.warning("Failed to attach SysLogHandler %s:%s: %s", host, port, exc)

    logger.info(
        "MCP logging configured level=%s syslog=%s",
        level_name,
        _env("SYSLOG_SERVER", "") or "off",
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
    LOG_LEVEL / SYSLOG_SERVER
        Shared with the app and nginx. ``SYSLOG_SERVER=host[:port]`` dual-writes
        MCP logs to rsyslog (UDP 514 default) in addition to stderr.
    """
    configure_mcp_logging()
    transport = (_env("MCP_TRANSPORT", "stdio") or "stdio").strip().lower()
    if transport in {"http", "streamable-http", "sse"}:
        host = _env("MCP_HOST", "127.0.0.1") or "127.0.0.1"
        port = int(_env("MCP_PORT", "8001") or "8001")
        path = _env("MCP_PATH", "/mcp") or "/mcp"
        # Default stateless for HTTP so reverse proxies / multi-instance work.
        stateless_raw = _env("MCP_STATELESS_HTTP", "1") or "1"
        stateless = stateless_raw.strip().lower() in {"1", "true", "yes", "on"}
        logger.info(
            "Starting MCP transport=%s bind=%s:%s path=%s",
            transport,
            host,
            port,
            path,
        )
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
    logger.info("Starting MCP transport=stdio")
    mcp.run()
