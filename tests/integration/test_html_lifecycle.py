"""HTML multi-step lifecycle flows beyond the core create→complete→delete path."""

from __future__ import annotations

from urllib.parse import quote

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from integration.helpers import html_login, png_upload, seed_chore
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy
from qr_chores.models.rewards import PointLedger, UserAchievement
from qr_chores.models.user import User
from qr_chores.services.achievements import ensure_default_achievements
from qr_chores.services.points import points_balance


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qr_scan_login_next_then_complete(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    """Anonymous QR hit → login with next → confirm → complete → parent sees Done."""
    await html_login(client, parent_user.email, "parent-pass")
    create = await client.post(
        "/chores",
        data={
            "title": "Kitchen wipe",
            "description": "",
            "due_time": "22:00",
            "base_points": "8",
            "photo_policy": "none",
            "schedule_day": ["0", "1", "2", "3", "4", "5", "6"],
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    async with app.state.session_factory() as session:
        chore = (
            await session.execute(select(Chore).where(Chore.title == "Kitchen wipe"))
        ).scalar_one()
        token = chore.qr_token

    # Fresh client (no session) simulates phone scan before login
    from httpx import ASGITransport
    from httpx import AsyncClient as AC

    transport = ASGITransport(app=app)
    async with AC(transport=transport, base_url="http://testserver") as phone:
        anon = await phone.get(f"/c/{token}", follow_redirects=False)
        assert anon.status_code == 303
        loc = anon.headers["location"]
        assert "/login" in loc
        assert token in loc

        # Child logs in with next preserved
        next_path = f"/c/{token}"
        logged_in = await phone.post(
            "/login",
            data={
                "email": child_user.email,
                "password": "child-pass",
                "next": next_path,
            },
            follow_redirects=False,
        )
        assert logged_in.status_code == 303
        assert logged_in.headers["location"] == next_path

        confirm = await phone.get(next_path)
        assert confirm.status_code == 200
        assert "Kitchen wipe" in confirm.text
        assert "I did it" in confirm.text

        done = await phone.post(f"/c/{token}")
        assert done.status_code == 200
        assert "Kitchen wipe" in done.text

    await html_login(client, parent_user.email, "parent-pass")
    today = await client.get("/today")
    assert today.status_code == 200
    assert "Kitchen wipe" in today.text
    assert "Done" in today.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_deactivate_blocks_complete_reactivate_allows(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    """Deactivate stops the QR without deleting history; reactivate restores complete."""
    await html_login(client, parent_user.email, "parent-pass")
    create = await client.post(
        "/chores",
        data={
            "title": "Toggle me",
            "description": "",
            "due_time": "20:00",
            "base_points": "6",
            "photo_policy": "none",
            "schedule_day": ["0", "1", "2", "3", "4", "5", "6"],
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    async with app.state.session_factory() as session:
        chore = (
            await session.execute(select(Chore).where(Chore.title == "Toggle me"))
        ).scalar_one()
        chore_id = chore.id
        token = chore.qr_token

    # Child completes while active
    await html_login(client, child_user.email, "child-pass")
    assert (await client.post(f"/c/{token}")).status_code == 200

    async with app.state.session_factory() as session:
        balance_after_first = await points_balance(session, child_user.id)
        assert balance_after_first >= 6
        assert await session.scalar(select(func.count()).select_from(ChoreCompletion)) == 1

    # Parent deactivates
    await html_login(client, parent_user.email, "parent-pass")
    deact = await client.post(f"/chores/{chore_id}/deactivate", follow_redirects=False)
    assert deact.status_code == 303

    # Child cannot complete inactive QR
    await html_login(client, child_user.email, "child-pass")
    blocked = await client.get(f"/c/{token}")
    assert blocked.status_code == 404
    blocked_post = await client.post(f"/c/{token}")
    assert blocked_post.status_code == 404

    # History still visible to parent
    await html_login(client, parent_user.email, "parent-pass")
    history = await client.get("/history")
    assert "Toggle me" in history.text

    # Reactivate — QR works again, but already done same day
    react = await client.post(f"/chores/{chore_id}/activate", follow_redirects=False)
    assert react.status_code == 303

    await html_login(client, child_user.email, "child-pass")
    again = await client.post(f"/c/{token}")
    assert again.status_code == 200
    assert "already" in again.text.lower()

    async with app.state.session_factory() as session:
        assert await points_balance(session, child_user.id) == balance_after_first
        assert await session.scalar(select(func.count()).select_from(ChoreCompletion)) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mixed_photo_policies_same_day(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    """Parent creates optional + required chores; child completes each correctly."""
    await html_login(client, parent_user.email, "parent-pass")
    async with app.state.session_factory() as session:
        await ensure_default_achievements(session)
        await session.commit()

    for title, policy, points in (
        ("Optional trash", "optional", "5"),
        ("Required bed", "required", "12"),
        ("No photo sweep", "none", "4"),
    ):
        r = await client.post(
            "/chores",
            data={
                "title": title,
                "description": "",
                "due_time": "21:00",
                "base_points": points,
                "photo_policy": policy,
                "schedule_day": ["0", "1", "2", "3", "4", "5", "6"],
            },
            follow_redirects=False,
        )
        assert r.status_code == 303, title

    async with app.state.session_factory() as session:
        chores = {
            c.title: c
            for c in (await session.execute(select(Chore).where(Chore.is_active.is_(True))))
            .scalars()
            .all()
        }

    await html_login(client, child_user.email, "child-pass")

    # Optional: no photo OK
    opt = chores["Optional trash"]
    assert (await client.post(f"/c/{opt.qr_token}")).status_code == 200

    # Required: blocked then OK with photo
    req = chores["Required bed"]
    assert (await client.post(f"/c/{req.qr_token}")).status_code == 400
    assert (await client.post(f"/c/{req.qr_token}", files=png_upload())).status_code == 200

    # None: no photo field needed
    none = chores["No photo sweep"]
    assert (await client.post(f"/c/{none.qr_token}")).status_code == 200

    async with app.state.session_factory() as session:
        completions = list((await session.execute(select(ChoreCompletion))).scalars().all())
        assert len(completions) == 3
        by_chore = {c.chore_id: c for c in completions}
        assert by_chore[opt.id].photo_object_key is None
        assert by_chore[req.id].photo_object_key is not None
        assert by_chore[none.id].photo_object_key is None
        balance = await points_balance(session, child_user.id)
        # bases 5+12+4 = 21 plus timing + First Step achievement
        assert balance >= 21

    await html_login(client, parent_user.email, "parent-pass")
    today = await client.get("/today")
    assert today.status_code == 200
    for title in ("Optional trash", "Required bed", "No photo sweep"):
        assert title in today.text
    # All three done
    assert today.text.count("Done") >= 3

    history = await client.get("/history")
    assert "Required bed" in history.text
    assert "View photo" in history.text or "/photos/" in history.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_edit_preserves_qr_token_and_new_points_apply(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    """Editing a chore keeps the printed QR token; new base points apply on complete."""
    await html_login(client, parent_user.email, "parent-pass")
    create = await client.post(
        "/chores",
        data={
            "title": "Stable QR",
            "description": "v1",
            "due_time": "18:00",
            "base_points": "3",
            "photo_policy": "none",
            "schedule_day": ["0", "1", "2", "3", "4", "5", "6"],
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    async with app.state.session_factory() as session:
        chore = (
            await session.execute(select(Chore).where(Chore.title == "Stable QR"))
        ).scalar_one()
        chore_id = chore.id
        original_token = chore.qr_token

    edit = await client.post(
        f"/chores/{chore_id}/edit",
        data={
            "title": "Stable QR v2",
            "description": "updated",
            "due_time": "19:30",
            "base_points": "25",
            "photo_policy": "optional",
            "schedule_day": ["0", "1", "2", "3", "4", "5", "6"],
        },
        follow_redirects=False,
    )
    assert edit.status_code == 303

    async with app.state.session_factory() as session:
        updated = await session.get(Chore, chore_id)
        assert updated is not None
        assert updated.qr_token == original_token
        assert updated.title == "Stable QR v2"
        assert updated.base_points == 25
        assert updated.photo_policy == PhotoPolicy.optional

    # Same printed token still works; points use new base
    await html_login(client, child_user.email, "child-pass")
    confirm = await client.get(f"/c/{original_token}")
    assert confirm.status_code == 200
    assert "Stable QR v2" in confirm.text

    done = await client.post(f"/c/{original_token}")
    assert done.status_code == 200
    assert "25" in done.text or "+25" in done.text

    async with app.state.session_factory() as session:
        completion = (await session.execute(select(ChoreCompletion))).scalar_one()
        assert completion.points_awarded >= 25


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_complete_custom_achievement_threshold(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    """Parent sets threshold-2 achievement; unlocks only after second chore complete."""
    await html_login(client, parent_user.email, "parent-pass")
    created = await client.post(
        "/rewards/achievements",
        data={
            "title": "Double Duty",
            "description": "Finish two chores",
            "icon_key": "star",
            "criteria_type": "total_completions",
            "threshold": "2",
            "points_reward": "40",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303

    # Zero timing so balance math is stable
    await client.post(
        "/rewards/bonuses",
        data={
            "early_bonus_points": "0",
            "on_time_bonus_points": "0",
            "late_bonus_points": "0",
        },
        follow_redirects=False,
    )

    tokens: list[str] = []
    for title in ("Chore One", "Chore Two"):
        r = await client.post(
            "/chores",
            data={
                "title": title,
                "description": "",
                "due_time": "23:00",
                "base_points": "10",
                "photo_policy": "none",
                "schedule_day": ["0", "1", "2", "3", "4", "5", "6"],
            },
            follow_redirects=False,
        )
        assert r.status_code == 303

    async with app.state.session_factory() as session:
        for title in ("Chore One", "Chore Two"):
            chore = (await session.execute(select(Chore).where(Chore.title == title))).scalar_one()
            tokens.append(chore.qr_token)

    await html_login(client, child_user.email, "child-pass")

    first = await client.post(f"/c/{tokens[0]}")
    assert first.status_code == 200
    assert "Double Duty" not in first.text

    async with app.state.session_factory() as session:
        assert await points_balance(session, child_user.id) == 10
        unlocks = await session.scalar(
            select(func.count())
            .select_from(UserAchievement)
            .where(UserAchievement.user_id == child_user.id)
        )
        assert unlocks == 0

    second = await client.post(f"/c/{tokens[1]}")
    assert second.status_code == 200
    assert "Double Duty" in second.text

    async with app.state.session_factory() as session:
        # 10 + 10 base + 40 achievement
        assert await points_balance(session, child_user.id) == 60
        unlocks = (
            (
                await session.execute(
                    select(UserAchievement).where(UserAchievement.user_id == child_user.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(unlocks) == 1

    ach_page = await client.get("/me/achievements")
    assert ach_page.status_code == 200
    assert "Double Duty" in ach_page.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_deactivate_keeps_points_delete_removes_chore_history(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    """Points stay after deactivate; hard delete removes chore + completions but not ledger."""
    await html_login(client, parent_user.email, "parent-pass")
    create = await client.post(
        "/chores",
        data={
            "title": "Ephemeral",
            "description": "",
            "due_time": "20:00",
            "base_points": "15",
            "photo_policy": "required",
            "schedule_day": ["0", "1", "2", "3", "4", "5", "6"],
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    async with app.state.session_factory() as session:
        chore = (
            await session.execute(select(Chore).where(Chore.title == "Ephemeral"))
        ).scalar_one()
        chore_id = chore.id
        token = chore.qr_token

    await html_login(client, child_user.email, "child-pass")
    done = await client.post(f"/c/{token}", files=png_upload())
    assert done.status_code == 200

    async with app.state.session_factory() as session:
        balance = await points_balance(session, child_user.id)
        assert balance >= 15
        completion = (await session.execute(select(ChoreCompletion))).scalar_one()
        photo_key = completion.photo_object_key
        assert photo_key

    await html_login(client, parent_user.email, "parent-pass")
    await client.post(f"/chores/{chore_id}/deactivate", follow_redirects=False)

    async with app.state.session_factory() as session:
        # Points unchanged by deactivate
        assert await points_balance(session, child_user.id) == balance
        assert await session.get(Chore, chore_id) is not None
        assert await session.scalar(select(func.count()).select_from(ChoreCompletion)) == 1

    deleted = await client.post(f"/chores/{chore_id}/delete", follow_redirects=False)
    assert deleted.status_code == 303

    async with app.state.session_factory() as session:
        assert await session.get(Chore, chore_id) is None
        assert await session.scalar(select(func.count()).select_from(ChoreCompletion)) == 0
        # Ledger (earned points) remains — awards are not clawed back
        assert await points_balance(session, child_user.id) == balance
        ledger_count = await session.scalar(
            select(func.count())
            .select_from(PointLedger)
            .where(PointLedger.user_id == child_user.id)
        )
        assert ledger_count >= 1

    history = await client.get("/history")
    assert "Ephemeral" not in history.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_next_preserves_query_safe_path(
    client: AsyncClient,
    child_user: User,
    app,
) -> None:
    """QR login next is a relative path only; unsafe next is ignored after login."""
    chore = await seed_chore(app.state.session_factory, title="Next path chore")

    # Safe next lands on confirm
    safe = await client.post(
        "/login",
        data={
            "email": child_user.email,
            "password": "child-pass",
            "next": f"/c/{chore.qr_token}",
        },
        follow_redirects=False,
    )
    assert safe.status_code == 303
    assert safe.headers["location"] == f"/c/{chore.qr_token}"

    # Unsafe absolute URL must not redirect off-site
    from httpx import ASGITransport
    from httpx import AsyncClient as AC

    transport = ASGITransport(app=app)
    async with AC(transport=transport, base_url="http://testserver") as other:
        evil = await other.post(
            "/login",
            data={
                "email": child_user.email,
                "password": "child-pass",
                "next": "https://evil.example/phish",
            },
            follow_redirects=False,
        )
        assert evil.status_code == 303
        assert "evil.example" not in evil.headers["location"]
        assert evil.headers["location"] == "/home"

        # Encoded open redirect also blocked
        sneaky = await other.post(
            "/login",
            data={
                "email": child_user.email,
                "password": "child-pass",
                "next": quote("//evil.example", safe=""),
            },
            follow_redirects=False,
        )
        assert sneaky.status_code == 303
        assert "evil" not in sneaky.headers["location"]
