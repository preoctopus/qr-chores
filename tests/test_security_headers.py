"""Tests for the security response headers middleware."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from qr_chores.config import Settings, get_settings
from qr_chores.security_headers import SecurityHeadersMiddleware


@pytest.mark.asyncio
async def test_security_headers_present_on_html_response(client: AsyncClient) -> None:
    resp = await client.get("/login")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    csp = resp.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


@pytest.mark.asyncio
async def test_security_headers_present_on_api_response(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in resp.headers


@pytest.mark.asyncio
async def test_no_hsts_over_plain_http(client: AsyncClient, test_settings: Settings) -> None:
    # test_settings BASE_URL is http://testserver (no HSTS expected).
    assert not test_settings.base_url.startswith("https://")
    resp = await client.get("/login")
    assert "strict-transport-security" not in resp.headers


@pytest.mark.asyncio
async def test_hsts_when_base_url_is_https(
    monkeypatch: pytest.MonkeyPatch, test_settings: Settings
) -> None:
    monkeypatch.setenv("BASE_URL", "https://chores.example.com")
    get_settings.cache_clear()

    from httpx import ASGITransport

    from qr_chores.main import create_app

    application = create_app()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as https_client:
        resp = await https_client.get("/healthz")
        assert resp.headers["strict-transport-security"] == "max-age=63072000; includeSubDomains"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_hsts_when_x_forwarded_proto_is_https(client: AsyncClient) -> None:
    resp = await client.get("/login", headers={"x-forwarded-proto": "https"})
    assert resp.headers["strict-transport-security"] == "max-age=63072000; includeSubDomains"


@pytest.mark.asyncio
async def test_non_http_scope_bypasses_header_wrapping() -> None:
    calls: list[str] = []

    async def inner_app(scope, receive, send) -> None:
        calls.append(scope["type"])

    middleware = SecurityHeadersMiddleware(inner_app)

    async def receive():
        return {"type": "lifespan.startup"}

    async def send(message) -> None:
        return None

    await middleware({"type": "lifespan"}, receive, send)
    assert calls == ["lifespan"]

