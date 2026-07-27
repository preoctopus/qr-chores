"""API multi-step lifecycle flows: rewards, deactivate, stable QR, dual auth."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from integration.helpers import TINY_PNG, api_login, auth_header, png_upload
from qr_chores.models.chore import Chore, ChoreCompletion
from qr_chores.models.rewards import PointLedger, UserAchievement
from qr_chores.models.user import User
from qr_chores.services.points import points_balance


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_rewards_config_multi_complete_unlock(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    """Parent configures bonuses + threshold-2 achievement via API; child earns on 2nd complete."""
    parent_token = await api_login(client, parent_user.email, "parent-pass")
    parent_h = auth_header(parent_token)

    bonuses = await client.put(
        "/api/v1/rewards/bonuses",
        headers=parent_h,
        json={
            "early_bonus_points": 0,
            "on_time_bonus_points": 0,
            "late_bonus_points": 0,
        },
    )
    assert bonuses.status_code == 200

    ach = await client.post(
        "/api/v1/rewards/achievements",
        headers=parent_h,
        json={
            "title": "API Double",
            "description": "Two completes",
            "icon_key": "star",
            "criteria_type": "total_completions",
            "threshold": 2,
            "points_reward": 35,
        },
    )
    assert ach.status_code == 201, ach.text
    ach_id = ach.json()["id"]

    tokens: list[str] = []
    for title in ("API A", "API B"):
        created = await client.post(
            "/api/v1/chores",
            headers=parent_h,
            json={
                "title": title,
                "due_time": "23:59:00",
                "schedule_days": "0123456",
                "photo_policy": "none",
                "base_points": 10,
            },
        )
        assert created.status_code == 201, created.text
        tokens.append(created.json()["qr_token"])

    child_token = await api_login(client, child_user.email, "child-pass")
    child_h = auth_header(child_token)

    first = await client.post(f"/api/v1/c/{tokens[0]}/complete", headers=child_h)
    assert first.status_code == 200
    assert first.json()["points"]["base"] == 10
    assert first.json()["unlocks"] == []
    assert first.json()["points"]["achievement_points"] == 0

    second = await client.post(f"/api/v1/c/{tokens[1]}/complete", headers=child_h)
    assert second.status_code == 200
    body = second.json()
    assert body["points"]["base"] == 10
    assert body["points"]["achievement_points"] == 35
    assert body["points"]["total"] == 45
    assert any(u["title"] == "API Double" for u in body["unlocks"])

    async with app.state.session_factory() as session:
        # 10 + 10 + 35
        assert await points_balance(session, child_user.id) == 55
        assert (
            await session.scalar(
                select(func.count())
                .select_from(UserAchievement)
                .where(UserAchievement.user_id == child_user.id)
            )
            == 1
        )

    # Toggle achievement off — already unlocked stays; no further effect needed
    toggled = await client.post(
        f"/api/v1/rewards/achievements/{ach_id}/toggle",
        headers=parent_h,
    )
    assert toggled.status_code == 200
    assert toggled.json()["is_active"] is False

    achievements = await client.get("/api/v1/achievements", headers=child_h)
    assert achievements.status_code == 200
    # Inactive achievements are omitted from child list
    titles = [a["title"] for a in achievements.json()["achievements"]]
    assert "API Double" not in titles
    # But UserAchievement row still exists
    async with app.state.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(UserAchievement)) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_deactivate_reactivate_and_stable_qr(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    parent_token = await api_login(client, parent_user.email, "parent-pass")
    parent_h = auth_header(parent_token)

    created = await client.post(
        "/api/v1/chores",
        headers=parent_h,
        json={
            "title": "Stable API QR",
            "due_time": "21:00:00",
            "schedule_days": "0123456",
            "photo_policy": "optional",
            "base_points": 9,
        },
    )
    assert created.status_code == 201
    chore = created.json()
    chore_id = chore["id"]
    qr_token = chore["qr_token"]

    # Patch title and points — token must not change
    patched = await client.patch(
        f"/api/v1/chores/{chore_id}",
        headers=parent_h,
        json={"title": "Stable API QR renamed", "base_points": 18},
    )
    assert patched.status_code == 200
    assert patched.json()["qr_token"] == qr_token
    assert patched.json()["base_points"] == 18

    qr_info = await client.get(f"/api/v1/chores/{chore_id}/qr", headers=parent_h)
    assert qr_info.json()["qr_token"] == qr_token

    child_token = await api_login(client, child_user.email, "child-pass")
    child_h = auth_header(child_token)

    # Deactivate before complete → 404
    assert (
        await client.post(f"/api/v1/chores/{chore_id}/deactivate", headers=parent_h)
    ).status_code == 200
    assert (await client.post(f"/api/v1/c/{qr_token}/complete", headers=child_h)).status_code == 404

    # Reactivate and complete without photo (optional)
    assert (
        await client.post(f"/api/v1/chores/{chore_id}/activate", headers=parent_h)
    ).status_code == 200
    complete = await client.post(f"/api/v1/c/{qr_token}/complete", headers=child_h)
    assert complete.status_code == 200, complete.text
    assert complete.json()["chore"]["title"] == "Stable API QR renamed"
    assert complete.json()["points"]["base"] == 18
    assert complete.json()["completion"]["has_photo"] is False

    today = await client.get("/api/v1/today", headers=parent_h)
    row = next(r for r in today.json()["board"] if r["chore"]["id"] == chore_id)
    assert row["done"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_delete_removes_history_keeps_ledger(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    parent_token = await api_login(client, parent_user.email, "parent-pass")
    parent_h = auth_header(parent_token)

    created = await client.post(
        "/api/v1/chores",
        headers=parent_h,
        json={
            "title": "Delete me API",
            "due_time": "22:00:00",
            "schedule_days": "0123456",
            "photo_policy": "required",
            "base_points": 14,
        },
    )
    assert created.status_code == 201
    chore_id = created.json()["id"]
    qr_token = created.json()["qr_token"]

    child_token = await api_login(client, child_user.email, "child-pass")
    child_h = auth_header(child_token)
    complete = await client.post(
        f"/api/v1/c/{qr_token}/complete",
        headers=child_h,
        files=png_upload(),
    )
    assert complete.status_code == 200
    completion_id = complete.json()["completion"]["id"]

    # Photo readable by both roles
    assert (
        await client.get(f"/api/v1/photos/{completion_id}", headers=parent_h)
    ).status_code == 200
    assert (await client.get(f"/api/v1/photos/{completion_id}", headers=child_h)).status_code == 200

    async with app.state.session_factory() as session:
        balance = await points_balance(session, child_user.id)
        assert balance >= 14

    deleted = await client.delete(f"/api/v1/chores/{chore_id}", headers=parent_h)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    assert (await client.get(f"/api/v1/chores/{chore_id}", headers=parent_h)).status_code == 404
    assert (
        await client.get(f"/api/v1/photos/{completion_id}", headers=parent_h)
    ).status_code == 404

    history = await client.get("/api/v1/history", headers=parent_h)
    assert all(i["chore_id"] != chore_id for i in history.json()["items"])

    async with app.state.session_factory() as session:
        assert await session.get(Chore, chore_id) is None
        assert await session.scalar(select(func.count()).select_from(ChoreCompletion)) == 0
        assert await points_balance(session, child_user.id) == balance
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PointLedger)
                .where(PointLedger.user_id == child_user.id)
            )
        ) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_bearer_and_session_cookie_both_work(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    """HTML session cookie can call /api/v1; Bearer works without cookie."""
    # HTML login → session cookie on client
    login = await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
        follow_redirects=False,
    )
    assert login.status_code == 303

    me_cookie = await client.get("/api/v1/me")
    assert me_cookie.status_code == 200
    assert me_cookie.json()["role"] == "child"
    assert me_cookie.json()["email"] == child_user.email

    home_cookie = await client.get("/api/v1/home")
    assert home_cookie.status_code == 200

    # Parent bearer on a separate client
    from httpx import ASGITransport
    from httpx import AsyncClient as AC

    transport = ASGITransport(app=app)
    async with AC(transport=transport, base_url="http://testserver") as bare:
        parent_token = await api_login(bare, parent_user.email, "parent-pass")
        me_bearer = await bare.get("/api/v1/me", headers=auth_header(parent_token))
        assert me_bearer.status_code == 200
        assert me_bearer.json()["role"] == "parent"

        # Child cookie client still cannot hit parent API
        forbidden = await client.get("/api/v1/today")
        assert forbidden.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_parent_board_reflects_partial_day(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    """Today board shows mix of pending and done after one of two chores completed."""
    parent_token = await api_login(client, parent_user.email, "parent-pass")
    parent_h = auth_header(parent_token)

    ids: dict[str, int] = {}
    tokens: dict[str, str] = {}
    for title in ("Morning", "Evening"):
        created = await client.post(
            "/api/v1/chores",
            headers=parent_h,
            json={
                "title": title,
                "due_time": "12:00:00" if title == "Morning" else "20:00:00",
                "schedule_days": "0123456",
                "photo_policy": "none",
                "base_points": 5,
            },
        )
        assert created.status_code == 201
        body = created.json()
        ids[title] = body["id"]
        tokens[title] = body["qr_token"]

    child_token = await api_login(client, child_user.email, "child-pass")
    assert (
        await client.post(
            f"/api/v1/c/{tokens['Morning']}/complete",
            headers=auth_header(child_token),
        )
    ).status_code == 200

    today = await client.get("/api/v1/today", headers=parent_h)
    assert today.status_code == 200
    board = {row["chore"]["title"]: row for row in today.json()["board"]}
    assert board["Morning"]["done"] is True
    assert board["Evening"]["done"] is False

    # Child home board matches
    home = await client.get("/api/v1/home", headers=auth_header(child_token))
    home_board = {row["chore"]["title"]: row for row in home.json()["board"]}
    assert home_board["Morning"]["done"] is True
    assert home_board["Evening"]["done"] is False
    assert home.json()["done_count"] >= 1
    assert home.json()["total_count"] >= 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_optional_then_required_create_and_complete(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    """Full parent create → child complete path for optional and required policies."""
    parent_token = await api_login(client, parent_user.email, "parent-pass")
    parent_h = auth_header(parent_token)
    child_token = await api_login(client, child_user.email, "child-pass")
    child_h = auth_header(child_token)

    optional = await client.post(
        "/api/v1/chores",
        headers=parent_h,
        json={
            "title": "Optional dishes",
            "due_time": "23:30:00",
            "schedule_days": "0123456",
            "photo_policy": "optional",
            "base_points": 7,
        },
    )
    assert optional.status_code == 201
    opt_token = optional.json()["qr_token"]

    required = await client.post(
        "/api/v1/chores",
        headers=parent_h,
        json={
            "title": "Required vacuum",
            "due_time": "23:45:00",
            "schedule_days": "0123456",
            "photo_policy": "required",
            "base_points": 11,
        },
    )
    assert required.status_code == 201
    req_token = required.json()["qr_token"]

    # Optional without photo
    opt_done = await client.post(f"/api/v1/c/{opt_token}/complete", headers=child_h)
    assert opt_done.status_code == 200
    assert opt_done.json()["completion"]["has_photo"] is False

    # Required without photo fails
    req_miss = await client.post(f"/api/v1/c/{req_token}/complete", headers=child_h)
    assert req_miss.status_code == 400
    assert req_miss.json()["detail"]["code"] == "photo_required"

    # Required with photo
    req_done = await client.post(
        f"/api/v1/c/{req_token}/complete",
        headers=child_h,
        files=png_upload(),
    )
    assert req_done.status_code == 200
    assert req_done.json()["completion"]["has_photo"] is True
    completion_id = req_done.json()["completion"]["id"]

    history = await client.get("/api/v1/history", headers=parent_h)
    items = {i["chore_title"]: i for i in history.json()["items"]}
    assert items["Optional dishes"]["completion"]["has_photo"] is False
    assert items["Required vacuum"]["completion"]["has_photo"] is True

    photo = await client.get(f"/api/v1/photos/{completion_id}", headers=parent_h)
    assert photo.status_code == 200
    assert photo.content == TINY_PNG
