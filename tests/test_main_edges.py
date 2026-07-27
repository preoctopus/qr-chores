"""Coverage for main.py exception handlers, OpenAPI cache, and run()."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from qr_chores.config import get_settings
from qr_chores.main import create_app, lifespan, run


@pytest.mark.asyncio
async def test_openapi_schema_cached(client: AsyncClient, app) -> None:
    first = app.openapi()
    second = app.openapi()
    assert first is second
    # exercise path loop (parameters skip branch is rare; login remains public)
    assert "/api/v1/auth/login" in first["paths"]


@pytest.mark.asyncio
async def test_unhandled_exception_json_and_html(app) -> None:
    @app.get("/__test_boom__")
    async def _boom() -> None:
        raise RuntimeError("intentional boom")

    @app.get("/api/v1/__test_boom_api__")
    async def _boom_api() -> None:
        raise RuntimeError("api boom")

    # raise_app_exceptions=False so ServerErrorMiddleware 500 responses are visible
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        api = await client.get("/__test_boom__", headers={"Accept": "application/json"})
        assert api.status_code == 500
        assert api.json()["detail"] == "Internal server error"

        html = await client.get("/__test_boom__", headers={"Accept": "text/html"})
        assert html.status_code == 500
        assert "Something went wrong" in html.text or "try again" in html.text.lower()

        api_pref = await client.get(
            "/api/v1/__test_boom_api__",
            headers={"Accept": "text/html"},
        )
        assert api_pref.status_code == 500
        assert api_pref.json()["detail"] == "Internal server error"


@pytest.mark.asyncio
async def test_http_exception_edges(app) -> None:
    @app.get("/__test_teapot__")
    async def _teapot() -> None:
        raise HTTPException(status_code=418, detail="short and stout")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # HTML accept → error template for uncommon status codes
        teapot_html = await client.get(
            "/__test_teapot__",
            headers={"Accept": "text/html"},
        )
        assert teapot_html.status_code == 418
        assert "short and stout" in teapot_html.text or "Something" in teapot_html.text

        # JSON accept without text/html
        teapot_json = await client.get(
            "/__test_teapot__",
            headers={"Accept": "application/json"},
        )
        assert teapot_json.status_code == 418
        assert teapot_json.json()["detail"] == "short and stout"

        # 401 HTML with query string preserves next
        login_redirect = await client.get(
            "/today?filter=late",
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )
        assert login_redirect.status_code == 303
        loc = login_redirect.headers["location"]
        assert loc.startswith("/login?next=")
        assert "today" in loc
        assert "filter" in loc

        # 401 without HTML accept → JSON
        unauth_json = await client.get(
            "/today",
            headers={"Accept": "application/json"},
        )
        assert unauth_json.status_code == 401


def test_run_invokes_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "9999")
    with patch("uvicorn.run") as mock_run:
        run()
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        assert kwargs["port"] == 9999
        assert kwargs["host"] == "0.0.0.0"


@pytest.mark.asyncio
async def test_lifespan_runs_init(monkeypatch: pytest.MonkeyPatch, test_settings) -> None:
    """Lifespan configures logging and calls init_db."""
    called: list[str] = []

    async def fake_init_db() -> None:
        called.append("init_db")

    monkeypatch.setattr("qr_chores.main.init_db", fake_init_db)
    monkeypatch.setattr(
        "qr_chores.main.configure_logging",
        lambda settings: called.append("configure_logging"),
    )
    get_settings.cache_clear()
    application = create_app()
    async with lifespan(application):
        pass
    assert "init_db" in called
    assert "configure_logging" in called
    get_settings.cache_clear()
