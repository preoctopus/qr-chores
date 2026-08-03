"""Tests for login rate limiting (in-process brute-force protection)."""

import pytest
from fastapi import Request
from httpx import AsyncClient

from qr_chores.config import Settings
from qr_chores.models.user import User
from qr_chores.services.auth_rate_limit import (
    LoginRateLimiter,
    get_client_ip,
    get_login_rate_limiter,
)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset rate limiter before and after each test."""
    get_login_rate_limiter().reset()
    yield
    get_login_rate_limiter().reset()


def test_get_client_ip():
    # Socket client host fallback
    req1 = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("192.168.1.50", 12345),
        }
    )
    assert get_client_ip(req1) == "192.168.1.50"

    # X-Forwarded-For header takes precedence
    req2 = Request(
        {
            "type": "http",
            "headers": [(b"x-forwarded-for", b"203.0.113.195, 70.41.3.18")],
            "client": ("192.168.1.50", 12345),
        }
    )
    assert get_client_ip(req2) == "203.0.113.195"

    # Fallback to localhost if no client or header
    req3 = Request({"type": "http", "headers": []})
    assert get_client_ip(req3) == "127.0.0.1"


def test_login_rate_limiter_unit():
    settings = Settings(login_rate_limit_attempts=3, login_rate_limit_window_seconds=60)
    limiter = LoginRateLimiter()
    ip = "10.0.0.1"
    email = "TestUser@example.com"

    assert not limiter.is_rate_limited(ip, email, settings)

    # 2 failures -> not rate limited yet
    limiter.record_failure(ip, email, settings)
    limiter.record_failure(ip, email, settings)
    assert not limiter.is_rate_limited(ip, email, settings)

    # 3rd failure -> rate limited
    limiter.record_failure(ip, email, settings)
    assert limiter.is_rate_limited(ip, email, settings)

    # Different email or IP is not rate limited
    assert not limiter.is_rate_limited("10.0.0.2", email, settings)
    assert not limiter.is_rate_limited(ip, "other@example.com", settings)

    # Record success clears state
    limiter.record_success(ip, email)
    assert not limiter.is_rate_limited(ip, email, settings)


@pytest.mark.asyncio
async def test_html_login_rate_limiting(client: AsyncClient, parent_user: User):
    # Perform failed attempts up to limit (default 5)
    for _ in range(5):
        resp = await client.post(
            "/login",
            data={"email": "dad@example.com", "password": "wrong-password"},
        )
        assert resp.status_code == 401

    # 6th attempt should be blocked by rate limiter (429)
    resp = await client.post(
        "/login",
        data={"email": "dad@example.com", "password": "wrong-password"},
    )
    assert resp.status_code == 429
    assert "Too many failed login attempts" in resp.text

    # Even if correct password is provided while locked out, it remains blocked
    resp_locked = await client.post(
        "/login",
        data={"email": "dad@example.com", "password": "parent-pass"},
    )
    assert resp_locked.status_code == 429

    # Resetting limiter unblocks login
    get_login_rate_limiter().reset()
    resp_ok = await client.post(
        "/login",
        data={"email": "dad@example.com", "password": "parent-pass"},
    )
    assert resp_ok.status_code == 303


@pytest.mark.asyncio
async def test_api_login_rate_limiting(client: AsyncClient, parent_user: User):
    # Perform failed attempts up to limit (default 5)
    for _ in range(5):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "dad@example.com", "password": "wrong-password"},
        )
        assert resp.status_code == 401

    # 6th attempt should be blocked by rate limiter (429)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "dad@example.com", "password": "wrong-password"},
    )
    assert resp.status_code == 429
    assert resp.json()["detail"] == "Too many failed login attempts. Please try again later."
