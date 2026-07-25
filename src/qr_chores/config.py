"""Application configuration from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "QR Chores"
    secret_key: str = "dev-only-change-me"
    database_url: str = "sqlite+aiosqlite:///./data/qr_chores.db"
    app_timezone: str = "America/Chicago"
    base_url: str = "http://127.0.0.1:8765"
    session_cookie_name: str = "qr_chores_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 14  # 14 days
    # Timing windows (minutes)
    on_time_grace_minutes: int = 15
    early_window_minutes: int = 60
    # Seed script defaults (override in env for real use)
    seed_parent_password: str = "parent-pass"
    seed_child_password: str = "child-pass"


@lru_cache
def get_settings() -> Settings:
    return Settings()
