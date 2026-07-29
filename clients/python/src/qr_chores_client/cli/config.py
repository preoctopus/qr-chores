"""Persistent credentials and CLI configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
APP_NAME = "qrc"
CREDENTIALS_FILENAME = "credentials.json"


def credentials_path() -> Path:
    """Return the path to the credentials file (creates parent dir lazily on write)."""
    override = os.environ.get("QRC_CONFIG_DIR")
    if override:
        return Path(override) / CREDENTIALS_FILENAME
    return Path(user_config_dir(APP_NAME, appauthor=False)) / CREDENTIALS_FILENAME


@dataclass
class Credentials:
    base_url: str = DEFAULT_BASE_URL
    access_token: str | None = None
    user: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> Credentials:
        p = path or credentials_path()
        if not p.is_file():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        return cls(
            base_url=str(raw.get("base_url") or DEFAULT_BASE_URL),
            access_token=raw.get("access_token") or None,
            user=dict(raw.get("user") or {}),
        )

    def save(self, path: Path | None = None) -> Path:
        p = path or credentials_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "base_url": self.base_url,
            "access_token": self.access_token,
            "user": self.user,
        }
        p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        try:
            p.chmod(0o600)
        except OSError:
            pass
        return p

    def clear_token(self, path: Path | None = None) -> Path:
        self.access_token = None
        self.user = {}
        return self.save(path)


@dataclass
class RuntimeConfig:
    """Resolved options for a single CLI invocation."""

    base_url: str
    access_token: str | None
    as_json: bool = False
    no_color: bool = False
    verbose: bool = False
    credentials: Credentials = field(default_factory=Credentials)


def resolve_base_url(
    cli_value: str | None = None,
    *,
    credentials: Credentials | None = None,
) -> str:
    """Priority: CLI flag → QRC_BASE_URL → QR_CHORES_BASE_URL → credentials → default."""
    if cli_value:
        return cli_value.rstrip("/")
    for env_key in ("QRC_BASE_URL", "QR_CHORES_BASE_URL"):
        env = os.environ.get(env_key)
        if env:
            return env.rstrip("/")
    if credentials and credentials.base_url:
        return credentials.base_url.rstrip("/")
    return DEFAULT_BASE_URL


def resolve_token(
    cli_value: str | None = None,
    *,
    credentials: Credentials | None = None,
) -> str | None:
    """Priority: CLI flag → QRC_TOKEN → stored credentials."""
    if cli_value:
        return cli_value
    env = os.environ.get("QRC_TOKEN")
    if env:
        return env
    if credentials:
        return credentials.access_token
    return None
