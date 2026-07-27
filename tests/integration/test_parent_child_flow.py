"""Integration: parent creates chores → child completes → parent observes."""

from datetime import time
from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy
from qr_chores.models.rewards import PointLedger, UserAchievement
from qr_chores.models.user import User
from qr_chores.services.achievements import ensure_default_achievements
from qr_chores.services.points import points_balance
from qr_chores.services.qr import new_qr_token

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _login(client: AsyncClient, email: str, password: str) -> None:
    r = await client.post(
        "/login",
        data={"email": email, "password": password, "next": ""},
        follow_redirects=False,
    )
    assert r.status_code == 303


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_chore_lifecycle(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    # Parent: seed achievements, create chore with required photo
    await _login(client, parent_user.email, "parent-pass")
    async with app.state.session_factory() as session:
        await ensure_default_achievements(session)
        await session.commit()

    create = await client.post(
        "/chores",
        data={
            "title": "Living room tidy",
            "description": "Pick up floor",
            "due_time": "21:00",
            "base_points": "10",
            "photo_policy": "required",
            "schedule_day": ["0", "1", "2", "3", "4", "5", "6"],
            "assignee_user_id": str(child_user.id),
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    assert "/qr" in create.headers["location"]

    async with app.state.session_factory() as session:
        chore = (
            await session.execute(select(Chore).where(Chore.title == "Living room tidy"))
        ).scalar_one()
        token = chore.qr_token
        chore_id = chore.id

    # Parent can see QR + print sheet
    assert (await client.get(f"/chores/{chore_id}/qr")).status_code == 200
    png = await client.get(f"/chores/{chore_id}/qr.png")
    assert png.status_code == 200
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert "Living room tidy" in (await client.get("/print/qrs")).text

    # Child: complete with photo → celebration / first achievement
    await _login(client, child_user.email, "child-pass")
    home = await client.get("/home")
    assert home.status_code == 200
    assert "Total points" in home.text
    assert "Awarded Achievements" in home.text
    assert "Living room tidy" not in home.text

    blocked = await client.post(f"/c/{token}")
    assert blocked.status_code == 400

    done = await client.post(
        f"/c/{token}",
        files={"photo": ("proof.png", BytesIO(TINY_PNG), "image/png")},
    )
    assert done.status_code == 200
    assert "Living room tidy" in done.text
    assert "First Step" in done.text

    # Child: points + achievements pages
    home2 = await client.get("/home")
    assert home2.status_code == 200
    assert "Total points" in home2.text or "points" in home2.text.lower()
    ach = await client.get("/me/achievements")
    assert ach.status_code == 200
    assert "First Step" in ach.text

    # Parent: today + history show completion and photo
    await _login(client, parent_user.email, "parent-pass")
    today = await client.get("/today")
    assert today.status_code == 200
    assert "Living room tidy" in today.text
    assert "Done" in today.text

    history = await client.get("/history")
    assert history.status_code == 200
    assert "Living room tidy" in history.text

    async with app.state.session_factory() as session:
        completion = (
            await session.execute(
                select(ChoreCompletion).where(ChoreCompletion.chore_id == chore_id)
            )
        ).scalar_one()
        assert completion.photo_object_key
        assert completion.user_id == child_user.id
        balance = await points_balance(session, child_user.id)
        assert balance >= 10
        unlocks = (
            (
                await session.execute(
                    select(UserAchievement).where(UserAchievement.user_id == child_user.id)
                )
            )
            .scalars()
            .all()
        )
        assert unlocks
        ledger = (
            (await session.execute(select(PointLedger).where(PointLedger.user_id == child_user.id)))
            .scalars()
            .all()
        )
        assert ledger

        photo = await client.get(f"/photos/{completion.id}")
        assert photo.status_code == 200
        assert photo.content[:8] == b"\x89PNG\r\n\x1a\n"

    # Parent deletes chore (history + photo cascade)
    confirm = await client.get(f"/chores/{chore_id}/delete")
    assert confirm.status_code == 200
    assert "Living room tidy" in confirm.text
    deleted = await client.post(f"/chores/{chore_id}/delete", follow_redirects=False)
    assert deleted.status_code == 303
    async with app.state.session_factory() as session:
        assert await session.get(Chore, chore_id) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_rewards_config_affects_completion(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    await _login(client, parent_user.email, "parent-pass")
    # Configure large early+on_time bonus so wall clock does not flake
    r = await client.post(
        "/rewards/bonuses",
        data={
            "early_bonus_points": "20",
            "on_time_bonus_points": "20",
            "late_bonus_points": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    created = await client.post(
        "/rewards/achievements",
        data={
            "title": "Integration Badge",
            "description": "First completion in this flow",
            "icon_key": "star",
            "criteria_type": "total_completions",
            "threshold": "1",
            "points_reward": "50",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303

    async with app.state.session_factory() as session:
        chore = Chore(
            title="Bonus chore",
            qr_token=new_qr_token(),
            due_time=time(23, 59),
            schedule_days="0123456",
            photo_policy=PhotoPolicy.none,
            base_points=5,
            is_active=True,
        )
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        token = chore.qr_token

    await _login(client, child_user.email, "child-pass")
    done = await client.post(f"/c/{token}")
    assert done.status_code == 200
    assert "Integration Badge" in done.text

    async with app.state.session_factory() as session:
        balance = await points_balance(session, child_user.id)
        # base 5 + timing 20 + achievement 50 = 75
        assert balance >= 75
