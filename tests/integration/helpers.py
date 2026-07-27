"""Shared helpers for multi-step integration flows."""

from __future__ import annotations

from datetime import time
from io import BytesIO

from httpx import AsyncClient

from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.services.qr import new_qr_token

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def html_login(client: AsyncClient, email: str, password: str) -> None:
    r = await client.post(
        "/login",
        data={"email": email, "password": password, "next": ""},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text


async def api_login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def seed_chore(session_factory, **kwargs) -> Chore:
    defaults = {
        "title": "Integration chore",
        "description": None,
        "qr_token": new_qr_token(),
        "due_time": time(23, 59),
        "schedule_days": "0123456",
        "photo_policy": PhotoPolicy.none,
        "base_points": 10,
        "is_active": True,
    }
    defaults.update(kwargs)
    async with session_factory() as session:
        chore = Chore(**defaults)
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        return chore


def png_upload() -> dict:
    return {"photo": ("proof.png", BytesIO(TINY_PNG), "image/png")}
