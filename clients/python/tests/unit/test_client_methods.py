"""Unit tests: every client method happy path via respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from qr_chores_client import QrChoresClient
from qr_chores_client.models import (
    AchievementCreate,
    AchievementUpdate,
    ChoreCreate,
    ChoreUpdate,
)

BASE = "https://api.example.test"

USER = {
    "id": 2,
    "email": "child@example.com",
    "display_name": "Child",
    "role": "child",
    "points_balance": 42,
}

CHORE = {
    "id": 1,
    "title": "Unload dishwasher",
    "description": "Empty top rack first",
    "qr_token": "qr-active-1",
    "due_time": "20:00:00",
    "schedule_days": "0123456",
    "photo_policy": "optional",
    "base_points": 10,
    "is_active": True,
}

COMPLETION = {
    "id": 1,
    "local_date": "2026-07-26",
    "completed_at": "2026-07-26T12:00:00Z",
    "timing": "on_time",
    "points_awarded": 12,
    "has_photo": True,
}

BOARD_ITEM = {
    "chore": CHORE,
    "done": True,
    "status_label": "Done",
    "status_kind": "done",
    "is_late_pending": False,
    "timing": "on_time",
    "completion": COMPLETION,
}

ACHIEVEMENT_ADMIN = {
    "id": 1,
    "title": "Early bird",
    "description": "Complete early 5 times",
    "icon_key": "bird",
    "criteria_type": "complete_early_count",
    "threshold": 5,
    "points_reward": 25,
    "is_active": True,
}

TINY_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


@pytest.fixture
async def client():
    c = QrChoresClient(BASE)
    yield c
    await c.aclose()


@respx.mock
async def test_login_stores_token(client: QrChoresClient):
    respx.post(f"{BASE}/api/v1/auth/login").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "child-token",
                "token_type": "bearer",
                "expires_in": 1209600,
                "user": USER,
            },
        )
    )
    tok = await client.login("child@example.com", "child-pass")
    assert tok.access_token == "child-token"
    assert client.access_token == "child-token"
    assert tok.user.role == "child"


@respx.mock
async def test_logout_clears_token(client: QrChoresClient):
    client.access_token = "child-token"
    respx.post(f"{BASE}/api/v1/auth/logout").mock(return_value=httpx.Response(204))
    await client.logout()
    assert client.access_token is None


@respx.mock
async def test_get_me(client: QrChoresClient):
    client.access_token = "t"
    route = respx.get(f"{BASE}/api/v1/me").mock(return_value=httpx.Response(200, json=USER))
    me = await client.get_me()
    assert me.email == USER["email"]
    assert route.calls[0].request.headers["Authorization"] == "Bearer t"


@respx.mock
async def test_get_home(client: QrChoresClient):
    client.access_token = "t"
    respx.get(f"{BASE}/api/v1/home").mock(
        return_value=httpx.Response(
            200,
            json={
                "local_date": "2026-07-26",
                "points_balance": 42,
                "points_today": 12,
                "done_count": 1,
                "total_count": 2,
                "board": [BOARD_ITEM],
                "recent_unlocks": [],
            },
        )
    )
    home = await client.get_home()
    assert home.points_balance == 42
    assert len(home.board) == 1


@respx.mock
async def test_get_confirm(client: QrChoresClient):
    client.access_token = "t"
    respx.get(f"{BASE}/api/v1/c/qr-active-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "chore": CHORE,
                "scheduled_today": True,
                "already_done": False,
                "is_late_pending": False,
                "completion": None,
            },
        )
    )
    conf = await client.get_confirm("qr-active-1")
    assert conf.chore.qr_token == "qr-active-1"
    assert conf.already_done is False


@respx.mock
async def test_complete_chore_without_photo(client: QrChoresClient):
    client.access_token = "t"
    respx.post(f"{BASE}/api/v1/c/qr-active-1/complete").mock(
        return_value=httpx.Response(
            200,
            json={
                "already_done": False,
                "chore": CHORE,
                "completion": COMPLETION,
                "points": {
                    "base": 10,
                    "timing_bonus": 2,
                    "achievement_points": 0,
                    "total": 12,
                },
                "unlocks": [],
            },
        )
    )
    result = await client.complete_chore("qr-active-1")
    assert result.points.total == 12
    assert result.already_done is False


@respx.mock
async def test_complete_chore_with_photo(client: QrChoresClient):
    client.access_token = "t"
    route = respx.post(f"{BASE}/api/v1/c/qr-photo-required/complete").mock(
        return_value=httpx.Response(
            200,
            json={
                "already_done": False,
                "chore": {**CHORE, "id": 2, "qr_token": "qr-photo-required"},
                "completion": {**COMPLETION, "id": 2, "has_photo": True},
                "points": {
                    "base": 5,
                    "timing_bonus": 2,
                    "achievement_points": 0,
                    "total": 7,
                },
                "unlocks": [],
            },
        )
    )
    result = await client.complete_chore(
        "qr-photo-required",
        photo=TINY_PNG,
        photo_filename="shot.png",
        photo_content_type="image/png",
    )
    assert result.completion.has_photo is True
    # multipart request body present
    content_type = route.calls[0].request.headers.get("content-type", "")
    assert "multipart" in content_type


@respx.mock
async def test_complete_chore_with_notes(client: QrChoresClient):
    client.access_token = "t"
    route = respx.post(f"{BASE}/api/v1/c/qr-active-1/complete").mock(
        return_value=httpx.Response(
            200,
            json={
                "already_done": False,
                "chore": CHORE,
                "completion": {**COMPLETION, "notes": "Need cat litter"},
                "points": {
                    "base": 10,
                    "timing_bonus": 2,
                    "achievement_points": 0,
                    "total": 12,
                },
                "unlocks": [],
            },
        )
    )
    result = await client.complete_chore("qr-active-1", notes="Need cat litter")
    assert result.completion.notes == "Need cat litter"
    assert b"notes=" in route.calls[0].request.content
    assert b"Need" in route.calls[0].request.content


@respx.mock
async def test_get_achievements(client: QrChoresClient):
    client.access_token = "t"
    respx.get(f"{BASE}/api/v1/achievements").mock(
        return_value=httpx.Response(
            200,
            json={
                "points_balance": 42,
                "unlocked_count": 0,
                "achievements": [
                    {
                        "id": 1,
                        "title": "Early bird",
                        "description": "x",
                        "icon_key": "bird",
                        "criteria_type": "complete_early_count",
                        "points_reward": 25,
                        "unlocked": False,
                        "progress": 0,
                        "threshold": 5,
                        "percent": 0,
                    }
                ],
            },
        )
    )
    ach = await client.get_achievements()
    assert ach.unlocked_count == 0
    assert ach.achievements[0].title == "Early bird"


@respx.mock
async def test_get_today(client: QrChoresClient):
    client.access_token = "t"
    respx.get(f"{BASE}/api/v1/today").mock(
        return_value=httpx.Response(
            200,
            json={"local_date": "2026-07-26", "board": [BOARD_ITEM]},
        )
    )
    today = await client.get_today()
    assert len(today.board) == 1


@respx.mock
async def test_get_history(client: QrChoresClient):
    client.access_token = "t"
    route = respx.get(f"{BASE}/api/v1/history").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "completion": COMPLETION,
                        "chore_id": 1,
                        "chore_title": "Unload dishwasher",
                        "user_id": 2,
                    }
                ],
                "limit": 10,
            },
        )
    )
    hist = await client.get_history(limit=10)
    assert hist.limit == 10
    assert hist.items[0].chore_title == "Unload dishwasher"
    assert route.calls[0].request.url.params["limit"] == "10"


@respx.mock
async def test_list_chores(client: QrChoresClient):
    client.access_token = "t"
    respx.get(f"{BASE}/api/v1/chores").mock(
        return_value=httpx.Response(200, json={"chores": [CHORE]})
    )
    listed = await client.list_chores(include_inactive=False)
    assert listed.chores[0].id == 1


@respx.mock
async def test_create_chore_model(client: QrChoresClient):
    client.access_token = "t"
    respx.post(f"{BASE}/api/v1/chores").mock(
        return_value=httpx.Response(201, json={**CHORE, "id": 4, "title": "New"})
    )
    created = await client.create_chore(
        ChoreCreate(title="New", due_time="18:00:00", photo_policy="optional")
    )
    assert created.title == "New"


@respx.mock
async def test_create_chore_dict(client: QrChoresClient):
    client.access_token = "t"
    respx.post(f"{BASE}/api/v1/chores").mock(
        return_value=httpx.Response(201, json={**CHORE, "id": 5})
    )
    created = await client.create_chore({"title": "X", "base_points": 3})
    assert created.id == 5


@respx.mock
async def test_get_chore(client: QrChoresClient):
    client.access_token = "t"
    respx.get(f"{BASE}/api/v1/chores/1").mock(return_value=httpx.Response(200, json=CHORE))
    chore = await client.get_chore(1)
    assert chore.title == CHORE["title"]


@respx.mock
async def test_update_chore(client: QrChoresClient):
    client.access_token = "t"
    respx.patch(f"{BASE}/api/v1/chores/1").mock(
        return_value=httpx.Response(200, json={**CHORE, "title": "Updated"})
    )
    chore = await client.update_chore(1, ChoreUpdate(title="Updated"))
    assert chore.title == "Updated"


@respx.mock
async def test_update_chore_dict_and_clear_description(client: QrChoresClient):
    client.access_token = "t"
    route = respx.patch(f"{BASE}/api/v1/chores/1").mock(
        return_value=httpx.Response(200, json={**CHORE, "description": None})
    )
    await client.update_chore(1, ChoreUpdate(clear_description=True))
    body = route.calls[0].request.content
    assert b"clear_description" in body


@respx.mock
async def test_delete_chore(client: QrChoresClient):
    client.access_token = "t"
    respx.delete(f"{BASE}/api/v1/chores/1").mock(
        return_value=httpx.Response(
            200,
            json={"deleted": True, "chore_id": 1, "completions_removed": 1},
        )
    )
    result = await client.delete_chore(1)
    assert result.deleted is True
    assert result.completions_removed == 1


@respx.mock
async def test_activate_deactivate(client: QrChoresClient):
    client.access_token = "t"
    respx.post(f"{BASE}/api/v1/chores/3/activate").mock(
        return_value=httpx.Response(200, json={**CHORE, "id": 3, "is_active": True})
    )
    respx.post(f"{BASE}/api/v1/chores/1/deactivate").mock(
        return_value=httpx.Response(200, json={**CHORE, "is_active": False})
    )
    a = await client.activate_chore(3)
    d = await client.deactivate_chore(1)
    assert a.is_active is True
    assert d.is_active is False


@respx.mock
async def test_get_qr_info_and_png(client: QrChoresClient):
    client.access_token = "t"
    respx.get(f"{BASE}/api/v1/chores/1/qr").mock(
        return_value=httpx.Response(
            200,
            json={
                "chore_id": 1,
                "title": "Unload dishwasher",
                "qr_token": "qr-active-1",
                "qr_url": "http://test/c/qr-active-1",
                "png_path": "/api/v1/chores/1/qr.png",
            },
        )
    )
    respx.get(f"{BASE}/api/v1/chores/1/qr.png").mock(
        return_value=httpx.Response(200, content=TINY_PNG, headers={"content-type": "image/png"})
    )
    info = await client.get_qr_info(1)
    png = await client.get_qr_png(1)
    assert info.qr_token == "qr-active-1"
    assert png.startswith(b"\x89PNG")


@respx.mock
async def test_rewards_flow(client: QrChoresClient):
    client.access_token = "t"
    respx.get(f"{BASE}/api/v1/rewards").mock(
        return_value=httpx.Response(
            200,
            json={
                "bonuses": {
                    "early_bonus_points": 5,
                    "on_time_bonus_points": 2,
                    "late_bonus_points": 0,
                },
                "achievements": [ACHIEVEMENT_ADMIN],
            },
        )
    )
    respx.put(f"{BASE}/api/v1/rewards/bonuses").mock(
        return_value=httpx.Response(
            200,
            json={
                "early_bonus_points": 7,
                "on_time_bonus_points": 3,
                "late_bonus_points": 1,
            },
        )
    )
    respx.post(f"{BASE}/api/v1/rewards/achievements").mock(
        return_value=httpx.Response(201, json={**ACHIEVEMENT_ADMIN, "id": 2, "title": "Streak"})
    )
    respx.patch(f"{BASE}/api/v1/rewards/achievements/1").mock(
        return_value=httpx.Response(200, json={**ACHIEVEMENT_ADMIN, "title": "Early bird v2"})
    )
    respx.post(f"{BASE}/api/v1/rewards/achievements/1/toggle").mock(
        return_value=httpx.Response(200, json={**ACHIEVEMENT_ADMIN, "is_active": False})
    )

    rewards = await client.get_rewards()
    assert rewards.bonuses.early_bonus_points == 5
    bonuses = await client.update_bonuses(
        early_bonus_points=7, on_time_bonus_points=3, late_bonus_points=1
    )
    assert bonuses.early_bonus_points == 7
    created = await client.create_achievement(
        AchievementCreate(title="Streak", criteria_type="streak_days", threshold=3)
    )
    assert created.title == "Streak"
    updated = await client.update_achievement(1, AchievementUpdate(title="Early bird v2"))
    assert updated.title == "Early bird v2"
    toggled = await client.toggle_achievement(1)
    assert toggled.is_active is False


@respx.mock
async def test_create_update_achievement_dict(client: QrChoresClient):
    client.access_token = "t"
    respx.post(f"{BASE}/api/v1/rewards/achievements").mock(
        return_value=httpx.Response(201, json=ACHIEVEMENT_ADMIN)
    )
    respx.patch(f"{BASE}/api/v1/rewards/achievements/1").mock(
        return_value=httpx.Response(200, json=ACHIEVEMENT_ADMIN)
    )
    await client.create_achievement({"title": "X", "criteria_type": "total_completions"})
    await client.update_achievement(1, {"title": "Y"})


@respx.mock
async def test_get_photo(client: QrChoresClient):
    client.access_token = "t"
    respx.get(f"{BASE}/api/v1/photos/1").mock(
        return_value=httpx.Response(200, content=TINY_PNG, headers={"content-type": "image/png"})
    )
    photo = await client.get_photo(1)
    assert photo.startswith(b"\x89PNG")


@respx.mock
async def test_login_failure(client: QrChoresClient):
    from qr_chores_client import AuthError

    respx.post(f"{BASE}/api/v1/auth/login").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid email or password."})
    )
    with pytest.raises(AuthError):
        await client.login("bad@example.com", "nope")


@respx.mock
async def test_context_manager():
    async with QrChoresClient(BASE) as client:
        respx.get(f"{BASE}/api/v1/me").mock(return_value=httpx.Response(200, json=USER))
        client.access_token = "t"
        me = await client.get_me()
        assert me.id == 2


def test_set_access_token():
    c = QrChoresClient(BASE)
    c.set_access_token("abc")
    assert c.access_token == "abc"
    c.set_access_token(None)
    assert c.access_token is None


def test_model_helpers():
    update = ChoreUpdate(title="T", clear_description=False)
    assert "clear_description" not in update.to_payload()
    update2 = ChoreUpdate(clear_description=True)
    assert update2.to_payload()["clear_description"] is True
    ach = AchievementUpdate(title="A")
    assert ach.to_payload() == {"title": "A"}


@respx.mock
async def test_model_dump_jsonable(client: QrChoresClient):
    client.access_token = "t"
    respx.get(f"{BASE}/api/v1/me").mock(return_value=httpx.Response(200, json=USER))
    me = await client.get_me()
    dumped = client.model_dump_jsonable(me)
    assert dumped["email"] == USER["email"]


@respx.mock
async def test_binary_endpoints_return_raw_bytes(client: QrChoresClient):
    client.access_token = "t"
    respx.get(f"{BASE}/api/v1/chores/1/qr.png").mock(
        return_value=httpx.Response(
            200, content=b"{}", headers={"content-type": "application/json"}
        )
    )
    # expect_json=False always returns response body bytes
    data = await client.get_qr_png(1)
    assert data == b"{}"


@respx.mock
async def test_logout_clears_token_even_on_error(client: QrChoresClient):
    """Logout is best-effort: 401 does not raise; token is still cleared."""
    client.access_token = "bad"
    respx.post(f"{BASE}/api/v1/auth/logout").mock(
        return_value=httpx.Response(401, json={"detail": "Not authenticated"})
    )
    await client.logout()
    assert client.access_token is None


@respx.mock
async def test_undo_completion(client: QrChoresClient):
    client.access_token = "parent-token"
    respx.post(f"{BASE}/api/v1/completions/10/undo").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "completion_id": 10,
                "chore_id": 1,
                "points_reverted": 12,
            },
        )
    )
    res = await client.undo_completion(10)
    assert res.success is True
    assert res.completion_id == 10
    assert res.points_reverted == 12
