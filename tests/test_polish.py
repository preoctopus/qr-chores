"""Phase 5 polish: print sheet, error pages, empty states."""

from datetime import time

import pytest
from httpx import AsyncClient

from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.models.user import User
from qr_chores.services.qr import new_qr_token


async def _login_parent(client: AsyncClient, parent_user: User) -> None:
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )


async def _create_chore(session_factory, **kwargs) -> Chore:
    defaults = {
        "title": "Print me",
        "description": None,
        "qr_token": new_qr_token(),
        "due_time": time(18, 0),
        "schedule_days": "0123456",
        "photo_policy": PhotoPolicy.required,
        "base_points": 15,
        "is_active": True,
    }
    defaults.update(kwargs)
    async with session_factory() as session:
        chore = Chore(**defaults)
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        return chore


@pytest.mark.asyncio
async def test_print_sheet_empty(client: AsyncClient, parent_user: User) -> None:
    await _login_parent(client, parent_user)
    response = await client.get("/print/qrs")
    assert response.status_code == 200
    assert "Nothing to print" in response.text
    assert "/chores/new" in response.text


@pytest.mark.asyncio
async def test_print_sheet_with_chores(client: AsyncClient, parent_user: User, app) -> None:
    await _login_parent(client, parent_user)
    chore = await _create_chore(app.state.session_factory, title="Kitchen wipe")
    response = await client.get("/print/qrs")
    assert response.status_code == 200
    assert "Kitchen wipe" in response.text
    assert "Photo required" in response.text
    assert f"/chores/{chore.id}/qr.png" in response.text
    assert "Cut on dashed lines" in response.text
    assert "window.print" in response.text or "Print sheet" in response.text


@pytest.mark.asyncio
async def test_html_404_page(client: AsyncClient) -> None:
    response = await client.get(
        "/this-route-does-not-exist",
        headers={"Accept": "text/html"},
    )
    assert response.status_code == 404
    assert "Page not found" in response.text
    assert "Go home" in response.text


@pytest.mark.asyncio
async def test_html_403_page(client: AsyncClient, child_user: User) -> None:
    await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
    )
    response = await client.get("/chores", headers={"Accept": "text/html"})
    assert response.status_code == 403
    assert "Not allowed" in response.text


@pytest.mark.asyncio
async def test_parent_today_empty_state(client: AsyncClient, parent_user: User) -> None:
    await _login_parent(client, parent_user)
    response = await client.get("/today")
    assert response.status_code == 200
    assert "Quiet day" in response.text or "No chores" in response.text
    assert "/chores/new" in response.text


@pytest.mark.asyncio
async def test_entrypoint_script_exists() -> None:
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "entrypoint.sh"
    assert script.is_file()
    text = script.read_text()
    assert "alembic upgrade head" in text
    assert "uvicorn" in text
