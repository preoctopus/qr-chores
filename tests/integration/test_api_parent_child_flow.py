"""Integration: parent creates chore via API → child completes → parent observes."""

from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from qr_chores.models.chore import ChoreCompletion
from qr_chores.models.rewards import PointLedger
from qr_chores.models.user import User
from qr_chores.services.points import points_balance

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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_parent_create_child_complete_parent_history(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
) -> None:
    parent_token = await _api_login(client, parent_user.email, "parent-pass")
    parent_headers = _auth(parent_token)

    # Parent: create chore with required photo
    created = await client.post(
        "/api/v1/chores",
        headers=parent_headers,
        json={
            "title": "API living room tidy",
            "description": "Pick up floor",
            "due_time": "21:00:00",
            "schedule_days": "0123456",
            "photo_policy": "required",
            "base_points": 10,
            "assignee_user_id": child_user.id,
        },
    )
    assert created.status_code == 201, created.text
    chore = created.json()
    chore_id = chore["id"]
    qr_token = chore["qr_token"]
    assert qr_token

    # Parent sees it on today board and QR endpoints
    today = await client.get("/api/v1/today", headers=parent_headers)
    assert today.status_code == 200
    titles = [row["chore"]["title"] for row in today.json()["board"]]
    assert "API living room tidy" in titles

    qr = await client.get(f"/api/v1/chores/{chore_id}/qr", headers=parent_headers)
    assert qr.status_code == 200
    assert qr.json()["qr_token"] == qr_token

    png = await client.get(f"/api/v1/chores/{chore_id}/qr.png", headers=parent_headers)
    assert png.status_code == 200
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"

    # Child: home → confirm → complete with photo
    child_token = await _api_login(client, child_user.email, "child-pass")
    child_headers = _auth(child_token)

    home = await client.get("/api/v1/home", headers=child_headers)
    assert home.status_code == 200
    assert any(row["chore"]["id"] == chore_id for row in home.json()["board"])

    confirm = await client.get(f"/api/v1/c/{qr_token}", headers=child_headers)
    assert confirm.status_code == 200
    assert confirm.json()["already_done"] is False
    assert confirm.json()["scheduled_today"] is True

    missing_photo = await client.post(f"/api/v1/c/{qr_token}/complete", headers=child_headers)
    assert missing_photo.status_code == 400
    assert missing_photo.json()["detail"]["code"] == "photo_required"

    complete = await client.post(
        f"/api/v1/c/{qr_token}/complete",
        headers=child_headers,
        files={"photo": ("proof.png", BytesIO(TINY_PNG), "image/png")},
    )
    assert complete.status_code == 200, complete.text
    done = complete.json()
    assert done["already_done"] is False
    assert done["points"]["total"] >= 10
    assert done["completion"]["has_photo"] is True
    completion_id = done["completion"]["id"]

    # Double-complete same day returns already_done
    again = await client.post(
        f"/api/v1/c/{qr_token}/complete",
        headers=child_headers,
        files={"photo": ("proof.png", BytesIO(TINY_PNG), "image/png")},
    )
    assert again.status_code == 200
    assert again.json()["already_done"] is True

    # Points landed in ledger
    async with app.state.session_factory() as session:
        balance = await points_balance(session, child_user.id)
        assert balance >= 10
        rows = (
            (
                await session.execute(
                    select(ChoreCompletion).where(ChoreCompletion.chore_id == chore_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        ledger = (
            (await session.execute(select(PointLedger).where(PointLedger.user_id == child_user.id)))
            .scalars()
            .all()
        )
        assert len(ledger) >= 1

    # Parent: history + photo + today status
    history = await client.get("/api/v1/history", headers=parent_headers)
    assert history.status_code == 200
    item = next(i for i in history.json()["items"] if i["chore_id"] == chore_id)
    assert item["completion"]["has_photo"] is True
    assert item["chore_title"] == "API living room tidy"

    photo = await client.get(f"/api/v1/photos/{completion_id}", headers=parent_headers)
    assert photo.status_code == 200
    assert photo.content == TINY_PNG

    today_after = await client.get("/api/v1/today", headers=parent_headers)
    board_row = next(r for r in today_after.json()["board"] if r["chore"]["id"] == chore_id)
    assert board_row["done"] is True
