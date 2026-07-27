"""OAuth 2.1 persistent storage services using SQLAlchemy."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.models.oauth import OAuthClient, OAuthCode, OAuthToken


def _json_dumps(obj: Any) -> str:
    if isinstance(obj, (list, tuple, set)):
        return json.dumps([str(x) for x in obj])
    return json.dumps(obj)


def _json_loads(data: str) -> list[str]:
    try:
        val = json.loads(data)
        if isinstance(val, list):
            return [str(x) for x in val]
    except Exception:
        pass
    return []


async def get_oauth_client(session: AsyncSession, client_id: str) -> OAuthClient | None:
    stmt = select(OAuthClient).where(OAuthClient.client_id == client_id)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def save_oauth_client(
    session: AsyncSession,
    client_id: str,
    client_name: str,
    redirect_uris: list[str],
    grant_types: list[str],
    response_types: list[str],
    token_endpoint_auth_method: str = "none",
    client_secret: str | None = None,
) -> OAuthClient:
    existing = await get_oauth_client(session, client_id)
    if existing:
        existing.client_name = client_name
        existing.redirect_uris_json = _json_dumps(redirect_uris)
        existing.grant_types_json = _json_dumps(grant_types)
        existing.response_types_json = _json_dumps(response_types)
        existing.token_endpoint_auth_method = token_endpoint_auth_method
        if client_secret is not None:
            existing.client_secret = client_secret
        client_obj = existing
    else:
        client_obj = OAuthClient(
            client_id=client_id,
            client_secret=client_secret,
            client_name=client_name,
            redirect_uris_json=_json_dumps(redirect_uris),
            grant_types_json=_json_dumps(grant_types),
            response_types_json=_json_dumps(response_types),
            token_endpoint_auth_method=token_endpoint_auth_method,
        )
        session.add(client_obj)

    await session.commit()
    await session.refresh(client_obj)
    return client_obj


async def create_oauth_code(
    session: AsyncSession,
    code: str,
    client_id: str,
    user_id: int,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    scopes: list[str],
    expires_at: datetime,
) -> OAuthCode:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    code_obj = OAuthCode(
        code=code,
        client_id=client_id,
        user_id=user_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        scopes_json=_json_dumps(scopes),
        expires_at=expires_at,
    )
    session.add(code_obj)
    await session.commit()
    await session.refresh(code_obj)
    return code_obj


async def get_oauth_code(session: AsyncSession, code: str) -> OAuthCode | None:
    stmt = select(OAuthCode).where(OAuthCode.code == code)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def delete_oauth_code(session: AsyncSession, code: str) -> None:
    stmt = delete(OAuthCode).where(OAuthCode.code == code)
    await session.execute(stmt)
    await session.commit()


async def create_oauth_token(
    session: AsyncSession,
    access_token: str,
    refresh_token: str | None,
    client_id: str,
    user_id: int,
    scopes: list[str],
    expires_at: datetime,
) -> OAuthToken:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    token_obj = OAuthToken(
        access_token=access_token,
        refresh_token=refresh_token,
        client_id=client_id,
        user_id=user_id,
        scopes_json=_json_dumps(scopes),
        expires_at=expires_at,
    )
    session.add(token_obj)
    await session.commit()
    await session.refresh(token_obj)
    return token_obj


async def get_oauth_token(session: AsyncSession, access_token: str) -> OAuthToken | None:
    stmt = select(OAuthToken).where(OAuthToken.access_token == access_token)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_oauth_token_by_refresh(
    session: AsyncSession, refresh_token: str
) -> OAuthToken | None:
    stmt = select(OAuthToken).where(OAuthToken.refresh_token == refresh_token)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def revoke_oauth_token(session: AsyncSession, token_str: str) -> None:
    stmt = delete(OAuthToken).where(
        (OAuthToken.access_token == token_str) | (OAuthToken.refresh_token == token_str)
    )
    await session.execute(stmt)
    await session.commit()
