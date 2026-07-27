"""Points ledger and achievements tests."""

from datetime import UTC, datetime, time, timedelta
from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from qr_chores.config import Settings
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy, TimingStatus
from qr_chores.models.rewards import Achievement, CriteriaType, PointLedger, UserAchievement
from qr_chores.models.user import User
from qr_chores.services.achievements import ensure_default_achievements, evaluate_achievements
from qr_chores.services.points import points_balance, set_setting
from qr_chores.services.qr import new_qr_token

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _create_chore(session_factory, **kwargs) -> Chore:
    defaults = {
        "title": "Chore",
        "description": None,
        "qr_token": new_qr_token(),
        "due_time": time(23, 59),  # hard to be late in tests
        "schedule_days": "0123456",
        "photo_policy": PhotoPolicy.none,
        "base_points": 10,
        "is_active": True,
    }
    defaults.update(kwargs)
    async with session_factory() as session:
        chore = Chore(**defaults)
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        return chore


async def _login(client: AsyncClient, email: str, password: str) -> None:
    await client.post("/login", data={"email": email, "password": password, "next": ""})


@pytest.mark.asyncio
async def test_complete_writes_ledger_and_first_step(
    client: AsyncClient, child_user: User, app, test_settings: Settings
) -> None:
    async with app.state.session_factory() as session:
        await ensure_default_achievements(session)
        await session.commit()

    chore = await _create_chore(app.state.session_factory, title="Sweep", base_points=10)
    await _login(client, child_user.email, "child-pass")
    resp = await client.post(f"/c/{chore.qr_token}")
    assert resp.status_code == 200
    assert "First Step" in resp.text
    # base 10 + First Step 10 = 20 (on-time bonus may add more)
    assert "+" in resp.text

    async with app.state.session_factory() as session:
        balance = await points_balance(session, child_user.id)
        assert balance >= 20
        ledger_count = await session.scalar(select(func.count()).select_from(PointLedger))
        assert ledger_count >= 2  # base + achievement (maybe timing too)
        unlocks = (
            (
                await session.execute(
                    select(UserAchievement).where(UserAchievement.user_id == child_user.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(unlocks) >= 1
        # Issue #10: points_awarded is chore-only; balance includes achievement ledger
        completion = (await session.execute(select(ChoreCompletion))).scalar_one()
        assert completion.points_awarded < balance
        achievement_pts = await session.scalar(
            select(func.coalesce(func.sum(PointLedger.delta), 0)).where(
                PointLedger.user_id == child_user.id,
                PointLedger.ref_type == "achievement",
            )
        )
        assert int(achievement_pts or 0) >= 10
        # base+timing column + achievement ledger == true balance (no double-count)
        assert completion.points_awarded + int(achievement_pts or 0) == balance


@pytest.mark.asyncio
async def test_timing_bonus_from_settings(client: AsyncClient, child_user: User, app) -> None:
    async with app.state.session_factory() as session:
        # Same bonus for early and on-time so wall-clock doesn't flake the test
        await set_setting(session, "early_bonus_points", "7")
        await set_setting(session, "on_time_bonus_points", "7")
        await set_setting(session, "late_bonus_points", "0")
        await session.commit()

    chore = await _create_chore(app.state.session_factory, base_points=5)
    await _login(client, child_user.email, "child-pass")
    await client.post(f"/c/{chore.qr_token}")

    async with app.state.session_factory() as session:
        balance = await points_balance(session, child_user.id)
        # 5 base + 7 timing (no achievements seeded)
        assert balance == 12
        reasons = (
            (
                await session.execute(
                    select(PointLedger.reason).where(PointLedger.user_id == child_user.id)
                )
            )
            .scalars()
            .all()
        )
        assert any("Timing" in r for r in reasons)


@pytest.mark.asyncio
async def test_streak_achievement_unlock(app, child_user: User, test_settings: Settings) -> None:
    async with app.state.session_factory() as session:
        ach = Achievement(
            title="Triple",
            description="3-day streak",
            icon_key="fire",
            criteria_type=CriteriaType.streak_days,
            criteria_json='{"days": 3}',
            points_reward=15,
            is_active=True,
        )
        session.add(ach)
        chore = Chore(
            title="Daily",
            qr_token=new_qr_token(),
            due_time=time(20, 0),
            schedule_days="0123456",
            photo_policy=PhotoPolicy.none,
            base_points=1,
            is_active=True,
        )
        session.add(chore)
        await session.flush()

        # Use app-local "today" (not system date.today()) so streak matches
        # evaluate_achievements / local_today(settings) under any CI timezone.
        from qr_chores.services.timeutil import local_today

        today = local_today(test_settings)
        for i in range(3):
            session.add(
                ChoreCompletion(
                    chore_id=chore.id,
                    user_id=child_user.id,
                    local_date=today - timedelta(days=2 - i),
                    completed_at=datetime.now(tz=UTC),
                    timing=TimingStatus.on_time,
                    points_awarded=1,
                )
            )
        await session.commit()

        unlocks = await evaluate_achievements(
            session, user_id=child_user.id, settings=test_settings
        )
        await session.commit()
        assert any(u.achievement.title == "Triple" for u in unlocks)
        balance = await points_balance(session, child_user.id)
        assert balance == 15


@pytest.mark.asyncio
async def test_parent_rewards_pages(client: AsyncClient, parent_user: User) -> None:
    await _login(client, parent_user.email, "parent-pass")
    page = await client.get("/rewards")
    assert page.status_code == 200
    assert "Timing bonuses" in page.text
    assert "First Step" in page.text or "Achievements" in page.text
    # Issue #5: plain-language Early / On time / Late rules on Rewards
    assert "How timing works" in page.text
    assert "Early" in page.text
    assert "On time" in page.text or "On-time" in page.text
    assert "grace" in page.text.lower()

    create = await client.post(
        "/rewards/achievements",
        data={
            "title": "Custom Win",
            "description": "Do 2 chores",
            "icon_key": "star",
            "criteria_type": "total_completions",
            "threshold": "2",
            "points_reward": "50",
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    bonuses = await client.post(
        "/rewards/bonuses",
        data={
            "early_bonus_points": "9",
            "on_time_bonus_points": "3",
            "late_bonus_points": "0",
        },
        follow_redirects=False,
    )
    assert bonuses.status_code == 303


@pytest.mark.asyncio
async def test_child_achievements_page(client: AsyncClient, child_user: User, app) -> None:
    async with app.state.session_factory() as session:
        await ensure_default_achievements(session)
        await session.commit()

    await _login(client, child_user.email, "child-pass")
    page = await client.get("/me/achievements")
    assert page.status_code == 200
    assert "First Step" in page.text
    assert "Locked" in page.text or "locked" in page.text.lower()


@pytest.mark.asyncio
async def test_photo_completion_counts_toward_achievement(
    client: AsyncClient, child_user: User, app, test_settings: Settings
) -> None:
    async with app.state.session_factory() as session:
        session.add(
            Achievement(
                title="Snapper",
                description="1 photo",
                icon_key="camera",
                criteria_type=CriteriaType.photo_completions,
                criteria_json='{"count": 1}',
                points_reward=8,
                is_active=True,
            )
        )
        await session.commit()

    chore = await _create_chore(
        app.state.session_factory,
        photo_policy=PhotoPolicy.required,
        base_points=3,
    )
    await _login(client, child_user.email, "child-pass")
    resp = await client.post(
        f"/c/{chore.qr_token}",
        files={"photo": ("p.png", BytesIO(TINY_PNG), "image/png")},
    )
    assert resp.status_code == 200
    assert "Snapper" in resp.text

    async with app.state.session_factory() as session:
        balance = await points_balance(session, child_user.id)
        assert balance >= 3 + 8
