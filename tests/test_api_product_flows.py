"""API-level product flows: points, achievements, photo policies end-to-end."""

from __future__ import annotations

from datetime import time
from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.models.rewards import Achievement, CriteriaType, PointLedger, UserAchievement
from qr_chores.models.user import User
from qr_chores.services.points import points_balance, set_setting
from qr_chores.services.qr import new_qr_token

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _api_login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_chore(session_factory, **kwargs) -> Chore:
    defaults = {
        "title": "API product chore",
        "description": None,
        "qr_token": new_qr_token(),
        "due_time": time(23, 59),
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


@pytest.mark.asyncio
async def test_api_complete_credits_points_and_unlocks(
    client: AsyncClient, child_user: User, app
) -> None:
    async with app.state.session_factory() as session:
        await set_setting(session, "early_bonus_points", "0")
        await set_setting(session, "on_time_bonus_points", "0")
        await set_setting(session, "late_bonus_points", "0")
        session.add(
            Achievement(
                title="API First",
                description="First via API",
                icon_key="spark",
                criteria_type=CriteriaType.total_completions,
                criteria_json='{"count": 1}',
                points_reward=20,
                is_active=True,
            )
        )
        await session.commit()

    chore = await _create_chore(
        app.state.session_factory, base_points=10, title="Dishes", assignee_user_id=child_user.id
    )
    token = await _api_login(client, child_user.email, "child-pass")
    headers = _auth(token)

    complete = await client.post(f"/api/v1/c/{chore.qr_token}/complete", headers=headers)
    assert complete.status_code == 200, complete.text
    body = complete.json()
    assert body["already_done"] is False
    assert body["points"]["base"] == 10
    assert body["points"]["timing_bonus"] == 0
    assert body["points"]["achievement_points"] == 20
    assert body["points"]["total"] == 30
    assert any(u["title"] == "API First" for u in body["unlocks"])

    async with app.state.session_factory() as session:
        assert await points_balance(session, child_user.id) == 30
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
        ledger = (
            (await session.execute(select(PointLedger).where(PointLedger.user_id == child_user.id)))
            .scalars()
            .all()
        )
        assert sum(e.delta for e in ledger) == 30
        assert any(e.ref_type == "completion" for e in ledger)
        assert any(e.ref_type == "achievement" for e in ledger)

    # Home reflects balance
    home = await client.get("/api/v1/home", headers=headers)
    assert home.status_code == 200
    assert home.json()["points_balance"] == 30

    # Achievements list shows unlock
    ach = await client.get("/api/v1/achievements", headers=headers)
    assert ach.status_code == 200
    data = ach.json()
    assert data["unlocked_count"] >= 1
    api_first = next(a for a in data["achievements"] if a["title"] == "API First")
    assert api_first["unlocked"] is True

    # Double complete: no extra points
    again = await client.post(f"/api/v1/c/{chore.qr_token}/complete", headers=headers)
    assert again.status_code == 200
    assert again.json()["already_done"] is True
    async with app.state.session_factory() as session:
        assert await points_balance(session, child_user.id) == 30
        assert await session.scalar(select(func.count()).select_from(UserAchievement)) == 1


@pytest.mark.asyncio
async def test_api_optional_photo_complete_without_file(
    client: AsyncClient, child_user: User, app
) -> None:
    chore = await _create_chore(
        app.state.session_factory,
        photo_policy=PhotoPolicy.optional,
        base_points=5,
        assignee_user_id=child_user.id,
    )
    token = await _api_login(client, child_user.email, "child-pass")
    headers = _auth(token)

    complete = await client.post(f"/api/v1/c/{chore.qr_token}/complete", headers=headers)
    assert complete.status_code == 200, complete.text
    body = complete.json()
    assert body["already_done"] is False
    assert body["completion"]["has_photo"] is False
    assert body["points"]["base"] == 5


@pytest.mark.asyncio
async def test_api_optional_photo_complete_with_file(
    client: AsyncClient, child_user: User, app
) -> None:
    chore = await _create_chore(
        app.state.session_factory, photo_policy=PhotoPolicy.optional, assignee_user_id=child_user.id
    )
    token = await _api_login(client, child_user.email, "child-pass")
    headers = _auth(token)

    complete = await client.post(
        f"/api/v1/c/{chore.qr_token}/complete",
        headers=headers,
        files={"photo": ("shot.png", BytesIO(TINY_PNG), "image/png")},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["completion"]["has_photo"] is True


@pytest.mark.asyncio
async def test_api_none_photo_policy_complete_without_file(
    client: AsyncClient, child_user: User, app
) -> None:
    chore = await _create_chore(
        app.state.session_factory, photo_policy=PhotoPolicy.none, assignee_user_id=child_user.id
    )
    token = await _api_login(client, child_user.email, "child-pass")
    complete = await client.post(
        f"/api/v1/c/{chore.qr_token}/complete",
        headers=_auth(token),
    )
    assert complete.status_code == 200
    assert complete.json()["completion"]["has_photo"] is False


@pytest.mark.asyncio
async def test_api_create_optional_chore_complete_without_photo(
    client: AsyncClient, parent_user: User, child_user: User, app
) -> None:
    """Parent creates optional-photo chore; child completes with no photo."""
    parent_token = await _api_login(client, parent_user.email, "parent-pass")
    created = await client.post(
        "/api/v1/chores",
        headers=_auth(parent_token),
        json={
            "title": "Optional tidy",
            "due_time": "23:59:00",
            "schedule_days": "0123456",
            "photo_policy": "optional",
            "base_points": 7,
            "assignee_user_id": child_user.id,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["photo_policy"] == "optional"
    qr_token = created.json()["qr_token"]

    child_token = await _api_login(client, child_user.email, "child-pass")
    complete = await client.post(
        f"/api/v1/c/{qr_token}/complete",
        headers=_auth(child_token),
    )
    assert complete.status_code == 200, complete.text
    body = complete.json()
    assert body["already_done"] is False
    assert body["completion"]["has_photo"] is False
    assert body["points"]["base"] == 7

    # Parent today board shows done
    today = await client.get("/api/v1/today", headers=_auth(parent_token))
    assert today.status_code == 200
    row = next(r for r in today.json()["board"] if r["chore"]["title"] == "Optional tidy")
    assert row["done"] is True


@pytest.mark.asyncio
async def test_api_create_required_chore_fails_without_photo(
    client: AsyncClient, parent_user: User, child_user: User, app
) -> None:
    """Parent creates required-photo chore; child cannot complete without proof."""
    parent_token = await _api_login(client, parent_user.email, "parent-pass")
    created = await client.post(
        "/api/v1/chores",
        headers=_auth(parent_token),
        json={
            "title": "Required proof",
            "due_time": "23:59:00",
            "schedule_days": "0123456",
            "photo_policy": "required",
            "base_points": 11,
            "assignee_user_id": child_user.id,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["photo_policy"] == "required"
    qr_token = created.json()["qr_token"]

    child_token = await _api_login(client, child_user.email, "child-pass")
    headers = _auth(child_token)

    missing = await client.post(f"/api/v1/c/{qr_token}/complete", headers=headers)
    assert missing.status_code == 400
    assert missing.json()["detail"]["code"] == "photo_required"

    ok = await client.post(
        f"/api/v1/c/{qr_token}/complete",
        headers=headers,
        files={"photo": ("proof.png", BytesIO(TINY_PNG), "image/png")},
    )
    assert ok.status_code == 200
    assert ok.json()["completion"]["has_photo"] is True
    assert ok.json()["points"]["base"] == 11
