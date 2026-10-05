"""Integration: child finishes one of two chores; next day the parent sees done + missed."""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from qr_chores.models.chore import Chore
from qr_chores.models.user import User
from qr_chores.services.timeutil import frozen_at

# Far enough ahead that chores created "now" already exist on these days.
MONDAY_MORNING = datetime(2030, 1, 7, 8, 0)
TUESDAY_MORNING = datetime(2030, 1, 8, 8, 0)


async def _login(client: AsyncClient, email: str, password: str) -> None:
    r = await client.post("/login", data={"email": email, "password": password, "next": ""})
    assert r.status_code == 303


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parent_sees_done_and_missed_next_day(
    client: AsyncClient, parent_user: User, child_user: User, app
) -> None:
    await _login(client, parent_user.email, "parent-pass")
    for title in ("Take out trash", "Walk the dog"):
        created = await client.post(
            "/chores",
            data={
                "title": title,
                "due_time": "21:00",
                "base_points": "10",
                "photo_policy": "none",
                "schedule_day": ["0", "1", "2", "3", "4", "5", "6"],
                "assignee_user_id": str(child_user.id),
            },
        )
        assert created.status_code == 303

    async with app.state.session_factory() as session:
        trash = (
            await session.execute(select(Chore).where(Chore.title == "Take out trash"))
        ).scalar_one()

    with frozen_at(MONDAY_MORNING):
        await _login(client, child_user.email, "child-pass")
        done = await client.post(f"/c/{trash.qr_token}")
        assert done.status_code == 200

        await _login(client, parent_user.email, "parent-pass")
        today = await client.get("/today")
        assert "1</strong> of 2 done" in today.text

    with frozen_at(TUESDAY_MORNING):
        api = await client.get("/api/v1/history/days?start_date=2030-01-07&end_date=2030-01-08")
        assert api.status_code == 200
        tue, mon = api.json()["days"]
        assert (tue["done"], tue["missed_count"], tue["open_count"]) == (0, 0, 2)
        assert (mon["done"], mon["missed_count"]) == (1, 1)
        assert mon["completions"][0]["chore_title"] == "Take out trash"
        assert mon["missed"][0]["chore_title"] == "Walk the dog"

        history = await client.get("/history?start_date=2030-01-07&end_date=2030-01-08")
        assert "Yesterday" in history.text
        assert "1 missed" in history.text
        assert "Walk the dog" in history.text
