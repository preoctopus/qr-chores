"""Unit tests for db helpers."""

from pathlib import Path

from qr_chores.db import ensure_sqlite_parent_dir


def test_ensure_sqlite_parent_dir_creates(tmp_path: Path) -> None:
    db_file = tmp_path / "nested" / "app.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    ensure_sqlite_parent_dir(url)
    assert db_file.parent.is_dir()


def test_ensure_sqlite_parent_dir_ignores_memory() -> None:
    ensure_sqlite_parent_dir("sqlite+aiosqlite:///:memory:")
    ensure_sqlite_parent_dir("postgresql+asyncpg://u:p@localhost/db")
