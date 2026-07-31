"""CLI smoke for qr-chores-reap-photos."""

from pathlib import Path

import pytest

from qr_chores.reap_photos import main


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "PHOTO_RETENTION_DAYS" in out or "retention" in out.lower()


def test_cli_dry_run_with_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    monkeypatch.setenv("PHOTO_STORAGE", "local")
    monkeypatch.setenv("PHOTO_LOCAL_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PHOTO_RETENTION_DAYS", "90")
    monkeypatch.setenv("BASE_URL", "http://testserver")
    from qr_chores.config import get_settings

    get_settings.cache_clear()

    # Create empty schema so the job can query.
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine

    from qr_chores.db import Base, ensure_sqlite_parent_dir

    async def _init() -> None:
        ensure_sqlite_parent_dir(f"sqlite+aiosqlite:///{db}")
        engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_init())

    with pytest.raises(SystemExit) as exc:
        main(["--dry-run"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "candidates=0" in out
    get_settings.cache_clear()
