"""Reap aged proof photo blobs while keeping completion history."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.config import Settings
from qr_chores.models.chore import ChoreCompletion
from qr_chores.services.storage import StorageError, get_photo_storage
from qr_chores.services.timeutil import local_today

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReapResult:
    """Outcome of a photo reaping pass."""

    retention_days: int
    cutoff_date: str
    candidates: int
    deleted: int
    failed: int
    cleared_keys: int
    dry_run: bool

    @property
    def skipped(self) -> bool:
        """True when retention is disabled (non-positive days)."""
        return self.retention_days <= 0


async def count_reap_candidates(
    db: AsyncSession,
    settings: Settings,
    *,
    retention_days: int | None = None,
) -> int:
    """Count completions that would be reaped (diagnostics / dry-run)."""
    days = settings.photo_retention_days if retention_days is None else retention_days
    if days <= 0:
        return 0
    cutoff = local_today(settings) - timedelta(days=days)
    n = await db.scalar(
        select(func.count())
        .select_from(ChoreCompletion)
        .where(
            ChoreCompletion.photo_object_key.is_not(None),
            ChoreCompletion.local_date < cutoff,
        )
    )
    return int(n or 0)


async def reap_old_photos(
    db: AsyncSession,
    settings: Settings,
    *,
    retention_days: int | None = None,
    dry_run: bool = False,
) -> ReapResult:
    """Delete photo objects older than the retention window and clear DB keys.

    Completions are selected by ``local_date`` (app timezone calendar day) so
    the window aligns with chore day boundaries. Rows keep points, timing, and
    ``had_photo`` for achievements; only the storage object and
    ``photo_object_key`` are removed.

    ``retention_days`` defaults to ``settings.photo_retention_days``. Values
    ``<= 0`` disable reaping (no-op success).
    """
    days = settings.photo_retention_days if retention_days is None else retention_days
    today = local_today(settings)
    if days <= 0:
        return ReapResult(
            retention_days=days,
            cutoff_date=today.isoformat(),
            candidates=0,
            deleted=0,
            failed=0,
            cleared_keys=0,
            dry_run=dry_run,
        )

    cutoff = today - timedelta(days=days)
    result = await db.execute(
        select(ChoreCompletion).where(
            ChoreCompletion.photo_object_key.is_not(None),
            ChoreCompletion.local_date < cutoff,
        )
    )
    rows = list(result.scalars().all())
    candidates = len(rows)

    if dry_run or not rows:
        return ReapResult(
            retention_days=days,
            cutoff_date=cutoff.isoformat(),
            candidates=candidates,
            deleted=0,
            failed=0,
            cleared_keys=0,
            dry_run=dry_run,
        )

    storage = get_photo_storage(settings)
    deleted = 0
    failed = 0
    cleared = 0

    for row in rows:
        key = row.photo_object_key
        if not key:
            continue
        try:
            storage.delete(key)
            deleted += 1
        except StorageError as exc:
            # Missing object: still clear the key so the UI does not 404 forever.
            if exc.code == "not_found":
                deleted += 1
            else:
                failed += 1
                logger.warning(
                    "photo_reap_delete_failed completion_id=%s key=%s code=%s: %s",
                    row.id,
                    key,
                    exc.code,
                    exc.message,
                )
                continue
        except Exception:  # noqa: BLE001 — isolate one bad object from the batch
            failed += 1
            logger.exception(
                "photo_reap_unexpected_error completion_id=%s key=%s",
                row.id,
                key,
            )
            continue

        row.photo_object_key = None
        # Ensure stats still credit photo completions after reaping.
        if not row.had_photo:
            row.had_photo = True
        cleared += 1

    await db.commit()
    logger.info(
        "photo_reap_done retention_days=%s cutoff=%s candidates=%s deleted=%s failed=%s cleared=%s",
        days,
        cutoff.isoformat(),
        candidates,
        deleted,
        failed,
        cleared,
    )
    return ReapResult(
        retention_days=days,
        cutoff_date=cutoff.isoformat(),
        candidates=candidates,
        deleted=deleted,
        failed=failed,
        cleared_keys=cleared,
        dry_run=False,
    )
