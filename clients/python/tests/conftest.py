"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport

from qr_chores_client import QrChoresClient
from qr_chores_client.cli.client_factory import set_test_transport

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

PARENT_EMAIL = "parent@example.com"
PARENT_PASSWORD = "parent-pass"
CHILD_EMAIL = "child@example.com"
CHILD_PASSWORD = "child-pass"

# Origin used with ASGI transport (host is ignored; paths are real).
MOCK_BASE_URL = "http://test"


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
def mock_app_sync():
    """Sync mock-api app fixture for CliRunner / SyncQrChoresClient tests."""
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


@pytest.fixture
def cli_mock_api(mock_app_sync, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Wire ``qrc`` to mock-api via ASGI + isolated credential dir."""
    monkeypatch.setenv("QRC_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("QRC_BASE_URL", raising=False)
    monkeypatch.delenv("QR_CHORES_BASE_URL", raising=False)
    monkeypatch.delenv("QRC_TOKEN", raising=False)
    transport = ASGITransport(app=mock_app_sync)
    set_test_transport(transport)
    try:
        yield {
            "base_url": MOCK_BASE_URL,
            "config_dir": tmp_path,
            "app": mock_app_sync,
        }
    finally:
        set_test_transport(None)
