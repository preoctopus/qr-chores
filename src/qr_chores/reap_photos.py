"""CLI entrypoint: delete aged proof photo blobs and clear storage keys."""

from __future__ import annotations

import argparse
import asyncio
import sys

from qr_chores.config import get_settings
from qr_chores.db import ensure_sqlite_parent_dir
from qr_chores.logging_setup import configure_logging
from qr_chores.services.photo_reap import reap_old_photos


async def _run(*, retention_days: int | None, dry_run: bool) -> int:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    settings = get_settings()
    configure_logging(settings)
    ensure_sqlite_parent_dir(settings.database_url)

    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            result = await reap_old_photos(
                db,
                settings,
                retention_days=retention_days,
                dry_run=dry_run,
            )
    finally:
        await engine.dispose()

    if result.skipped:
        print(
            f"photo reap skipped (retention_days={result.retention_days}; "
            "set PHOTO_RETENTION_DAYS > 0 to enable)"
        )
        return 0

    mode = "dry-run" if result.dry_run else "applied"
    print(
        f"photo reap {mode}: retention_days={result.retention_days} "
        f"cutoff={result.cutoff_date} candidates={result.candidates} "
        f"deleted={result.deleted} failed={result.failed} "
        f"cleared_keys={result.cleared_keys}"
    )
    # Non-zero only when every candidate failed and none were cleared.
    if (
        result.candidates > 0
        and result.cleared_keys == 0
        and result.failed > 0
        and not result.dry_run
    ):
        return 2
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="qr-chores-reap-photos",
        description=(
            "Delete proof photo objects older than PHOTO_RETENTION_DAYS and clear "
            "photo_object_key on those completions. History rows and had_photo stats remain."
        ),
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override PHOTO_RETENTION_DAYS for this run (default: env/settings).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count candidates only; do not delete objects or update the database.",
    )
    args = parser.parse_args(argv)

    try:
        code = asyncio.run(_run(retention_days=args.retention_days, dry_run=args.dry_run))
    except Exception as exc:  # noqa: BLE001
        print(f"photo reap failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    raise SystemExit(code)


if __name__ == "__main__":
    main()
