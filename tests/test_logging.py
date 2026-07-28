"""Logging setup, SYSLOG_SERVER parsing, and request action middleware."""

from __future__ import annotations

import logging
import logging.handlers
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from qr_chores.config import Settings, get_settings
from qr_chores.logging_setup import (
    configure_logging,
    log_user_action,
    parse_syslog_address,
    reset_logging_for_tests,
)


@pytest.fixture(autouse=True)
def _clean_logging() -> None:
    reset_logging_for_tests()
    yield
    reset_logging_for_tests()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", None),
        ("   ", None),
        ("rsyslog.internal", ("rsyslog.internal", 514)),
        ("rsyslog.internal:1514", ("rsyslog.internal", 1514)),
        ("udp://logs.example:514", ("logs.example", 514)),
        ("tcp://logs.example:601", ("logs.example", 601)),
        ("syslog://host", ("host", 514)),
        ("host:notaport", None),
        (":514", None),
    ],
)
def test_parse_syslog_address(raw: str, expected: tuple[str, int] | None) -> None:
    assert parse_syslog_address(raw) == expected


def test_settings_log_defaults() -> None:
    settings = Settings(
        secret_key="test-secret-key",
        database_url="sqlite+aiosqlite:///:memory:",
        base_url="http://testserver",
        environment="development",
    )
    assert settings.log_level == "INFO"
    assert settings.syslog_server == ""


def test_settings_syslog_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("BASE_URL", "http://testserver")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("SYSLOG_SERVER", "syslog.example:514")
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.log_level == "DEBUG"
        assert s.syslog_server == "syslog.example:514"
    finally:
        get_settings.cache_clear()


def test_configure_logging_console_only() -> None:
    settings = Settings(
        secret_key="test-secret-key",
        database_url="sqlite+aiosqlite:///:memory:",
        base_url="http://testserver",
        log_level="INFO",
        syslog_server="",
    )
    configure_logging(settings)
    root = logging.getLogger()
    assert root.level == logging.INFO
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert not any(isinstance(h, logging.handlers.SysLogHandler) for h in root.handlers)


def test_configure_logging_attaches_syslog() -> None:
    settings = Settings(
        secret_key="test-secret-key",
        database_url="sqlite+aiosqlite:///:memory:",
        base_url="http://testserver",
        log_level="INFO",
        syslog_server="127.0.0.1:5140",
    )
    fake = MagicMock()
    fake.level = logging.NOTSET
    fake.handle = MagicMock()
    with patch(
        "qr_chores.logging_setup.logging.handlers.SysLogHandler",
        return_value=fake,
    ) as ctor:
        configure_logging(settings)
        ctor.assert_called_once()
        assert ctor.call_args.kwargs.get("address") == ("127.0.0.1", 5140)
        fake.setLevel.assert_called()
        fake.setFormatter.assert_called()
    assert fake in logging.getLogger().handlers


def test_log_user_action_emits(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="qr_chores.actions"):
        log_user_action("login", user_id=3, detail="api", role="parent")
    assert any("event=login" in r.message and "user_id=3" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_action_middleware_logs_mutation(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="qr_chores.actions"):
        await client.post(
            "/login",
            data={"email": "nobody@example.com", "password": "x", "next": ""},
        )
    action_msgs = [r.message for r in caplog.records if r.name == "qr_chores.actions"]
    assert action_msgs, "expected action log records"
    assert any("method=POST" in m and "path=/login" in m for m in action_msgs) or any(
        "event=login_failed" in m for m in action_msgs
    )


@pytest.mark.asyncio
async def test_healthz_not_action_logged(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="qr_chores"):
        r1 = await client.get("/healthz")
        r2 = await client.get("/health")
        assert r1.status_code == 200
        assert r2.status_code == 200
    action_msgs = [r.message for r in caplog.records if r.name == "qr_chores.actions"]
    assert not any("/health" in m for m in action_msgs)
