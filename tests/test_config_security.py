"""Config hardening: SECRET_KEY defaults and production docs."""

import pytest
from pydantic import ValidationError

from qr_chores.config import Settings, get_settings
from qr_chores.main import create_app


def test_dev_default_secret_allowed_for_local_sqlite() -> None:
    settings = Settings(
        secret_key="dev-only-change-me",
        database_url="sqlite+aiosqlite:///:memory:",
        base_url="http://127.0.0.1:8765",
        environment="development",
    )
    assert settings.requires_strong_secret is False


def test_default_secret_rejected_for_https() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            secret_key="dev-only-change-me",
            database_url="sqlite+aiosqlite:///:memory:",
            base_url="https://chores.example.com",
            environment="development",
        )
    assert "SECRET_KEY" in str(exc.value)


def test_default_secret_rejected_for_postgres() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            secret_key="dev-only-change-me",
            database_url="postgresql+asyncpg://u:p@localhost/db",
            base_url="http://127.0.0.1:8765",
            environment="development",
        )
    assert "SECRET_KEY" in str(exc.value)


def test_default_secret_rejected_for_production_env() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            secret_key="dev-only-change-me",
            database_url="sqlite+aiosqlite:///:memory:",
            base_url="http://127.0.0.1:8765",
            environment="production",
        )
    assert "SECRET_KEY" in str(exc.value)


def test_strong_secret_ok_in_production() -> None:
    settings = Settings(
        secret_key="a-strong-random-secret-key-value",
        database_url="postgresql+asyncpg://u:p@localhost/db",
        base_url="https://chores.example.com",
        environment="production",
    )
    assert settings.is_production is True


def test_production_disables_openapi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "strong-prod-secret-for-tests")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("BASE_URL", "http://testserver")
    get_settings.cache_clear()
    try:
        app = create_app()
        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None
    finally:
        get_settings.cache_clear()


def test_development_keeps_openapi(test_settings) -> None:
    app = create_app()
    assert app.docs_url == "/docs"
    assert app.openapi_url == "/openapi.json"
