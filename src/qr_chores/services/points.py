"""Point ledger helpers."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.models.rewards import AppSetting, PointLedger

DEFAULT_BONUSES = {
    "early_bonus_points": "5",
    "on_time_bonus_points": "2",
    "late_bonus_points": "0",
}


async def get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    row = await db.get(AppSetting, key)
    if row is None:
        return default
    return row.value


async def set_setting(db: AsyncSession, key: str, value: str) -> None:
    row = await db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


async def get_timing_bonuses(db: AsyncSession) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, default in DEFAULT_BONUSES.items():
        raw = await get_setting(db, key, default)
        try:
            out[key] = int(raw)
        except ValueError:
            out[key] = int(default)
    return out


async def points_balance(db: AsyncSession, user_id: int) -> int:
    total = await db.scalar(
        select(func.coalesce(func.sum(PointLedger.delta), 0)).where(PointLedger.user_id == user_id)
    )
    return int(total or 0)


def add_ledger_entry(
    db: AsyncSession,
    *,
    user_id: int,
    delta: int,
    reason: str,
    ref_type: str | None = None,
    ref_id: int | None = None,
) -> PointLedger | None:
    if delta == 0:
        return None
    entry = PointLedger(
        user_id=user_id,
        delta=delta,
        reason=reason,
        ref_type=ref_type,
        ref_id=ref_id,
    )
    db.add(entry)
    return entry
