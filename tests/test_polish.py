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
async def test_print_sheet_with_chores(
    client: AsyncClient, parent_user: User, app, child_user: User
) -> None:
    await _login_parent(client, parent_user)
    chore = await _create_chore(
        app.state.session_factory, title="Kitchen wipe", assignee_user_id=child_user.id
    )
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


def test_user_documentation_exists_and_is_linked() -> None:
    """Issue #3: end-user guide for parents and child."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    user_doc = root / "docs" / "USER.md"
    readme = root / "README.md"
    assert user_doc.is_file()
    text = user_doc.read_text(encoding="utf-8")
    assert "Using QR Chores" in text
    assert "Early" in text and "On time" in text and "Late" in text
    assert "Parent guide" in text
    assert "Child guide" in text
    assert "BASE_URL" in text
    assert "Install as an app" in text
    assert "Add to Home screen" in text or "Add to Home Screen" in text
    readme_text = readme.read_text(encoding="utf-8")
    assert "docs/USER.md" in readme_text


@pytest.mark.asyncio
async def test_favicon_and_web_manifest(client: AsyncClient) -> None:
    """Favicon + web app manifest for browser tab and Add to Home Screen."""
    favicon = await client.get("/static/favicon.ico")
    assert favicon.status_code == 200
    assert favicon.content[:4] == b"\x00\x00\x01\x00"  # ICO magic

    logo_192 = await client.get("/static/icons/app-logo-192.png")
    assert logo_192.status_code == 200
    assert logo_192.headers["content-type"].startswith("image/png")
    assert logo_192.content[:8] == b"\x89PNG\r\n\x1a\n"

    logo_512 = await client.get("/static/icons/app-logo-512.png")
    assert logo_512.status_code == 200
    assert logo_512.headers["content-type"].startswith("image/png")

    # Old path should not remain (renamed to .webmanifest)
    assert (await client.get("/static/manifest.json")).status_code == 404

    manifest = await client.get("/static/manifest.webmanifest")
    assert manifest.status_code == 200
    assert "manifest" in manifest.headers.get("content-type", "")
    data = manifest.json()
    assert data["name"] == "ChoreQuest"
    assert data["short_name"] == "Chores"
    assert data["display"] == "standalone"
    assert data["start_url"] == "/"
    assert data["scope"] == "/"
    assert data["theme_color"] == "#7c5cff"
    assert data["background_color"] == "#0f1115"
    icon_srcs = {icon["src"] for icon in data["icons"]}
    assert "/static/icons/app-logo-192.png" in icon_srcs
    assert "/static/icons/app-logo-512.png" in icon_srcs
    assert all(icon.get("purpose") == "any" for icon in data["icons"])

    # Shell pages should wire favicon + manifest + install meta in <head>
    login = await client.get("/login")
    assert login.status_code == 200
    assert 'rel="icon" href="/static/favicon.ico"' in login.text
    assert 'rel="manifest" href="/static/manifest.webmanifest"' in login.text
    assert 'rel="apple-touch-icon" href="/static/icons/app-logo-192.png"' in login.text
    assert 'name="theme-color" content="#7c5cff"' in login.text
    assert 'name="apple-mobile-web-app-capable" content="yes"' in login.text
    assert 'name="mobile-web-app-capable" content="yes"' in login.text
    assert 'name="apple-mobile-web-app-title" content="Chores"' in login.text


@pytest.mark.asyncio
async def test_help_page_mobile_html(client: AsyncClient, parent_user: User) -> None:
    """In-app HTML guide is public and linked from login / shell."""
    help_page = await client.get("/help")
    assert help_page.status_code == 200
    assert "Using QR Chores" in help_page.text
    assert "Parent guide" in help_page.text
    assert "Child guide" in help_page.text
    assert "Install as an app" in help_page.text
    assert "Add to Home screen" in help_page.text
    assert "Add to Home Screen" in help_page.text
    assert "Chrome" in help_page.text
    assert "Safari" in help_page.text
    assert "Early" in help_page.text
    assert "On time" in help_page.text
    assert "Late" in help_page.text
    assert 'name="viewport"' in help_page.text

    login = await client.get("/login")
    assert login.status_code == 200
    assert 'href="/help"' in login.text

    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )
    today = await client.get("/today")
    assert today.status_code == 200
    assert 'href="/help"' in today.text
