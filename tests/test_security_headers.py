"""Security response headers middleware."""

import pytest
from httpx import ASGITransport, AsyncClient

from qr_chores.config import get_settings
from qr_chores.main import create_app
from qr_chores.services.storage import clear_photo_storage_cache


@pytest.mark.asyncio
async def test_security_headers_on_healthz(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-frame-options"] == "DENY"
    csp = response.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "strict-transport-security" not in response.headers


@pytest.mark.asyncio
async def test_security_headers_on_static(client: AsyncClient) -> None:
    response = await client.get("/static/css/app.css")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in response.headers


@pytest.mark.asyncio
async def test_security_headers_on_login_html(client: AsyncClient) -> None:
    response = await client.get("/login")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "style-src 'self' 'unsafe-inline'" in response.headers["content-security-policy"]


@pytest.mark.asyncio
async def test_docs_skip_csp_in_development(client: AsyncClient) -> None:
    """Swagger UI loads CDN assets; CSP is omitted on /docs only."""
    response = await client.get("/docs")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in response.headers


@pytest.mark.asyncio
async def test_hsts_when_base_url_is_https(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("SECRET_KEY", "a-strong-random-secret-key-value")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("BASE_URL", "https://chores.example.com")
    monkeypatch.setenv("PHOTO_STORAGE", "local")
    monkeypatch.setenv("PHOTO_LOCAL_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    clear_photo_storage_cache()
    try:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://testserver") as ac:
            response = await ac.get("/healthz")
        assert response.status_code == 200
        assert (
            response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
        )
        assert response.headers["x-content-type-options"] == "nosniff"
    finally:
        get_settings.cache_clear()
        clear_photo_storage_cache()
