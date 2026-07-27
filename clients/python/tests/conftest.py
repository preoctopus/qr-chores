"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from httpx import ASGITransport

from qr_chores_client import QrChoresClient

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

PARENT_EMAIL = "parent@example.com"
PARENT_PASSWORD = "parent-pass"
CHILD_EMAIL = "child@example.com"
CHILD_PASSWORD = "child-pass"


@pytest.fixture
def tiny_png() -> bytes:
    return TINY_PNG


@pytest.fixture
async def mock_app():
    from qr_chores_mock_api.app import app, reset_state

    reset_state()
    yield app
    reset_state()


@pytest.fixture
async def asgi_client(mock_app):
    transport = ASGITransport(app=mock_app)
    client = QrChoresClient("http://test", transport=transport)
    yield client
    await client.aclose()


@pytest.fixture
async def parent_client(mock_app):
    transport = ASGITransport(app=mock_app)
    client = QrChoresClient("http://test", transport=transport)
    await client.login(PARENT_EMAIL, PARENT_PASSWORD)
    yield client
    await client.aclose()


@pytest.fixture
async def child_client(mock_app):
    transport = ASGITransport(app=mock_app)
    client = QrChoresClient("http://test", transport=transport)
    await client.login(CHILD_EMAIL, CHILD_PASSWORD)
    yield client
    await client.aclose()
