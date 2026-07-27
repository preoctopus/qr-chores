"""Application configuration from environment variables."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known insecure default — allowed only for local SQLite + non-HTTPS BASE_URL.
_DEV_SECRET_KEY = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "QR Chores"
    # development | production — production disables OpenAPI docs
    environment: str = "development"
    secret_key: str = _DEV_SECRET_KEY
    database_url: str = "sqlite+aiosqlite:///./data/qr_chores.db"
    app_timezone: str = "America/Chicago"
    base_url: str = "http://127.0.0.1:8765"
    session_cookie_name: str = "qr_chores_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 14  # 14 days
    # Timing windows (minutes)
    on_time_grace_minutes: int = 15
    early_window_minutes: int = 60
    # Photo storage: "local" (dev) or "gcs" (Cloud Run)
    photo_storage: str = "local"
    photo_local_dir: str = "./data/uploads"
    gcs_bucket: str = ""
    photo_max_bytes: int = 5 * 1024 * 1024  # 5 MB
    # Seed script defaults (override in env for real use)
    seed_parent_password: str = "parent-pass"
    seed_child_password: str = "child-pass"
    # Admin registration API (POST /api/v1/admin/users). Empty disables admin routes.
    admin_api_key: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def requires_strong_secret(self) -> bool:
        """True when defaults are unsafe (HTTPS, Postgres, or explicit prod)."""
        if self.is_production:
            return True
        if self.base_url.startswith("https://"):
            return True
        url = self.database_url.lower()
        return "postgresql" in url or "asyncpg" in url or "postgres" in url

    @model_validator(mode="after")
    def _reject_insecure_secret_in_prod(self) -> "Settings":
        if self.secret_key == _DEV_SECRET_KEY and self.requires_strong_secret:
            raise ValueError(
                "SECRET_KEY must be set to a strong random value when using "
                "HTTPS BASE_URL, Postgres, or ENVIRONMENT=production. "
                "Do not use the default dev secret."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
