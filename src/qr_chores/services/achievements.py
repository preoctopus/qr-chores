"""Achievement evaluation and unlocks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.config import Settings
from qr_chores.models.chore import ChoreCompletion, TimingStatus
from qr_chores.models.rewards import Achievement, CriteriaType, UserAchievement
from qr_chores.services.points import add_ledger_entry
from qr_chores.services.timeutil import local_today


@dataclass
class UnlockedAchievement:
    achievement: Achievement
    points: int


def criteria_threshold(achievement: Achievement) -> int:
    """Parse the numeric threshold from achievement criteria_json.

    Streak achievements prefer ``days`` then ``count``; other criteria types
    prefer ``count`` then ``days``. Invalid or empty JSON defaults to 1.
    """
    try:
        data = json.loads(achievement.criteria_json or "{}")
    except json.JSONDecodeError:
        data = {}
    if achievement.criteria_type == CriteriaType.streak_days:
        return int(data.get("days", data.get("count", 1)))
    return int(data.get("count", data.get("days", 1)))


async def _count_completions(
    db: AsyncSession,
    user_id: int,
    *,
    timing: TimingStatus | None = None,
    with_photo: bool = False,
) -> int:
    q = select(func.count()).select_from(ChoreCompletion).where(ChoreCompletion.user_id == user_id)
    if timing is not None:
        q = q.where(ChoreCompletion.timing == timing)
    if with_photo:
        q = q.where(ChoreCompletion.photo_object_key.is_not(None))
    return int(await db.scalar(q) or 0)


async def _streak_days(db: AsyncSession, user_id: int, settings: Settings) -> int:
    """Consecutive local dates ending today (or yesterday if today has no completions yet) with at least one completion."""
    result = await db.execute(
        select(ChoreCompletion.local_date).where(ChoreCompletion.user_id == user_id).distinct()
    )
    days = {row[0] for row in result.all()}
    if not days:
        return 0
    today = local_today(settings)
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


async def progress_for(
    db: AsyncSession,
    user_id: int,
    achievement: Achievement,
    settings: Settings,
) -> int:
    ct = achievement.criteria_type
    if ct == CriteriaType.total_completions:
        return await _count_completions(db, user_id)
    if ct == CriteriaType.complete_on_time_count:
        return await _count_completions(db, user_id, timing=TimingStatus.on_time)
    if ct == CriteriaType.complete_early_count:
        return await _count_completions(db, user_id, timing=TimingStatus.early)
    if ct == CriteriaType.photo_completions:
        return await _count_completions(db, user_id, with_photo=True)
    if ct == CriteriaType.streak_days:
        return await _streak_days(db, user_id, settings)
    return 0


async def evaluate_achievements(
    db: AsyncSession,
    *,
    user_id: int,
    settings: Settings,
) -> list[UnlockedAchievement]:
    """Unlock any newly earned achievements; award points to ledger."""
    result = await db.execute(select(Achievement).where(Achievement.is_active.is_(True)))
    achievements = list(result.scalars().all())
    if not achievements:
        return []

    owned = await db.execute(
        select(UserAchievement.achievement_id).where(UserAchievement.user_id == user_id)
    )
    owned_ids = set(owned.scalars().all())

    unlocked: list[UnlockedAchievement] = []
    for ach in achievements:
        if ach.id in owned_ids:
            continue
        progress = await progress_for(db, user_id, ach, settings)
        if progress < criteria_threshold(ach):
            continue
        ua = UserAchievement(user_id=user_id, achievement_id=ach.id)
        db.add(ua)
        if ach.points_reward:
            add_ledger_entry(
                db,
                user_id=user_id,
                delta=ach.points_reward,
                reason=f"Achievement: {ach.title}",
                ref_type="achievement",
                ref_id=ach.id,
            )
        unlocked.append(UnlockedAchievement(achievement=ach, points=ach.points_reward))

    if unlocked:
        await db.flush()
    return unlocked


DEFAULT_ACHIEVEMENTS: list[dict] = [
    {
        "title": "First Step",
        "description": "Complete your first chore. You’re in.",
        "icon_key": "spark",
        "criteria_type": CriteriaType.total_completions,
        "criteria_json": '{"count": 1}',
        "points_reward": 10,
    },
    {
        "title": "On a Roll",
        "description": "Hit a 3-day streak. Keep the energy.",
        "icon_key": "fire",
        "criteria_type": CriteriaType.streak_days,
        "criteria_json": '{"days": 3}',
        "points_reward": 25,
    },
    {
        "title": "Week Legend",
        "description": "Seven days in a row. That’s main-character energy.",
        "icon_key": "crown",
        "criteria_type": CriteriaType.streak_days,
        "criteria_json": '{"days": 7}',
        "points_reward": 75,
    },
    {
        "title": "Early Bird",
        "description": "Finish early five times. Future you is grateful.",
        "icon_key": "bolt",
        "criteria_type": CriteriaType.complete_early_count,
        "criteria_json": '{"count": 5}',
        "points_reward": 30,
    },
    {
        "title": "On-Time Pro",
        "description": "Ten on-time completions. Clock’s best friend.",
        "icon_key": "clock",
        "criteria_type": CriteriaType.complete_on_time_count,
        "criteria_json": '{"count": 10}',
        "points_reward": 40,
    },
    {
        "title": "Photo Proof",
        "description": "Snap proof three times. Receipts secured.",
        "icon_key": "camera",
        "criteria_type": CriteriaType.photo_completions,
        "criteria_json": '{"count": 3}',
        "points_reward": 20,
    },
]


async def ensure_default_achievements(db: AsyncSession) -> int:
    """Seed stock achievements if none exist. Returns created count."""
    count = await db.scalar(select(func.count()).select_from(Achievement))
    if count and count > 0:
        return 0
    for spec in DEFAULT_ACHIEVEMENTS:
        db.add(
            Achievement(
                title=spec["title"],
                description=spec["description"],
                icon_key=spec["icon_key"],
                criteria_type=spec["criteria_type"],
                criteria_json=spec["criteria_json"],
                points_reward=spec["points_reward"],
                is_active=True,
            )
        )
    await db.flush()
    return len(DEFAULT_ACHIEVEMENTS)


ICON_CHOICES = [
    ("spark", "✨ Spark"),
    ("fire", "🔥 Fire"),
    ("crown", "👑 Crown"),
    ("bolt", "⚡ Bolt"),
    ("clock", "⏰ Clock"),
    ("camera", "📷 Camera"),
    ("star", "⭐ Star"),
    ("heart", "💜 Heart"),
]


CRITERIA_LABELS = {
    CriteriaType.total_completions: "Total completions",
    CriteriaType.complete_on_time_count: "On-time completions",
    CriteriaType.complete_early_count: "Early completions",
    CriteriaType.photo_completions: "Photo completions",
    CriteriaType.streak_days: "Day streak",
}
