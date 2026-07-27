"""Tests for SyncQrChoresClient."""

from __future__ import annotations

import httpx
import pytest
import respx

from qr_chores_client import SyncQrChoresClient

BASE = "https://api.example.test"

USER = {
    "id": 1,
    "email": "parent@example.com",
    "display_name": "Parent",
    "role": "parent",
    "points_balance": 0,
}

CHORE = {
    "id": 1,
    "title": "Unload dishwasher",
    "description": None,
    "qr_token": "qr-active-1",
    "due_time": "20:00:00",
    "schedule_days": "0123456",
    "photo_policy": "optional",
    "base_points": 10,
    "is_active": True,
}


@respx.mock
def test_sync_login_and_me():
    respx.post(f"{BASE}/api/v1/auth/login").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "parent-token",
                "token_type": "bearer",
                "expires_in": 100,
                "user": USER,
            },
        )
    )
    respx.get(f"{BASE}/api/v1/me").mock(return_value=httpx.Response(200, json=USER))
    respx.post(f"{BASE}/api/v1/auth/logout").mock(return_value=httpx.Response(204))

    with SyncQrChoresClient(BASE) as client:
        tok = client.login("parent@example.com", "parent-pass")
        assert tok.access_token == "parent-token"
        assert client.access_token == "parent-token"
        me = client.get_me()
        assert me.role == "parent"
        client.logout()
        assert client.access_token is None


@respx.mock
def test_sync_parent_methods():
    client = SyncQrChoresClient(BASE, access_token="parent-token")
    respx.get(f"{BASE}/api/v1/today").mock(
        return_value=httpx.Response(200, json={"local_date": "2026-07-26", "board": []})
    )
    respx.get(f"{BASE}/api/v1/history").mock(
        return_value=httpx.Response(200, json={"items": [], "limit": 50})
    )
    respx.get(f"{BASE}/api/v1/chores").mock(
        return_value=httpx.Response(200, json={"chores": [CHORE]})
    )
    respx.get(f"{BASE}/api/v1/chores/1").mock(return_value=httpx.Response(200, json=CHORE))
    respx.post(f"{BASE}/api/v1/chores").mock(return_value=httpx.Response(201, json=CHORE))
    respx.patch(f"{BASE}/api/v1/chores/1").mock(return_value=httpx.Response(200, json=CHORE))
    respx.post(f"{BASE}/api/v1/chores/1/activate").mock(
        return_value=httpx.Response(200, json=CHORE)
    )
    respx.post(f"{BASE}/api/v1/chores/1/deactivate").mock(
        return_value=httpx.Response(200, json={**CHORE, "is_active": False})
    )
    respx.delete(f"{BASE}/api/v1/chores/1").mock(
        return_value=httpx.Response(
            200, json={"deleted": True, "chore_id": 1, "completions_removed": 0}
        )
    )
    respx.get(f"{BASE}/api/v1/chores/1/qr").mock(
        return_value=httpx.Response(
            200,
            json={
                "chore_id": 1,
                "title": "x",
                "qr_token": "qr-active-1",
                "qr_url": "u",
                "png_path": "p",
            },
        )
    )
    respx.get(f"{BASE}/api/v1/chores/1/qr.png").mock(
        return_value=httpx.Response(200, content=b"PNGDATA", headers={"content-type": "image/png"})
    )
    respx.get(f"{BASE}/api/v1/rewards").mock(
        return_value=httpx.Response(
            200,
            json={
                "bonuses": {
                    "early_bonus_points": 5,
                    "on_time_bonus_points": 2,
                    "late_bonus_points": 0,
                },
                "achievements": [],
            },
        )
    )
    respx.put(f"{BASE}/api/v1/rewards/bonuses").mock(
        return_value=httpx.Response(
            200,
            json={
                "early_bonus_points": 1,
                "on_time_bonus_points": 1,
                "late_bonus_points": 0,
            },
        )
    )
    respx.post(f"{BASE}/api/v1/rewards/achievements").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 9,
                "title": "T",
                "description": "",
                "icon_key": "star",
                "criteria_type": "streak_days",
                "threshold": 1,
                "points_reward": 0,
                "is_active": True,
            },
        )
    )
    respx.patch(f"{BASE}/api/v1/rewards/achievements/9").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 9,
                "title": "T2",
                "description": "",
                "icon_key": "star",
                "criteria_type": "streak_days",
                "threshold": 1,
                "points_reward": 0,
                "is_active": True,
            },
        )
    )
    respx.post(f"{BASE}/api/v1/rewards/achievements/9/toggle").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 9,
                "title": "T2",
                "description": "",
                "icon_key": "star",
                "criteria_type": "streak_days",
                "threshold": 1,
                "points_reward": 0,
                "is_active": False,
            },
        )
    )
    respx.get(f"{BASE}/api/v1/photos/1").mock(
        return_value=httpx.Response(200, content=b"img", headers={"content-type": "image/png"})
    )

    try:
        assert client.get_today().board == []
        assert client.get_history().items == []
        assert client.list_chores().chores[0].id == 1
        assert client.get_chore(1).id == 1
        assert client.create_chore({"title": "X"}).id == 1
        assert client.update_chore(1, {"title": "Y"}).id == 1
        assert client.activate_chore(1).is_active is True
        assert client.deactivate_chore(1).is_active is False
        assert client.delete_chore(1).deleted is True
        assert client.get_qr_info(1).qr_token == "qr-active-1"
        assert client.get_qr_png(1) == b"PNGDATA"
        assert client.get_rewards().bonuses.early_bonus_points == 5
        assert (
            client.update_bonuses(
                early_bonus_points=1, on_time_bonus_points=1, late_bonus_points=0
            ).early_bonus_points
            == 1
        )
        assert client.create_achievement({"title": "T", "criteria_type": "streak_days"}).id == 9
        assert client.update_achievement(9, {"title": "T2"}).title == "T2"
        assert client.toggle_achievement(9).is_active is False
        assert client.get_photo(1) == b"img"
        client.set_access_token("other")
        assert client.access_token == "other"
    finally:
        client.close()


@respx.mock
def test_sync_child_methods():
    client = SyncQrChoresClient(BASE, access_token="child-token")
    respx.get(f"{BASE}/api/v1/home").mock(
        return_value=httpx.Response(
            200,
            json={
                "local_date": "2026-07-26",
                "points_balance": 0,
                "points_today": 0,
                "done_count": 0,
                "total_count": 0,
                "board": [],
                "recent_unlocks": [],
            },
        )
    )
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
    respx.post(f"{BASE}/api/v1/c/qr-active-1/complete").mock(
        return_value=httpx.Response(
            200,
            json={
                "already_done": False,
                "chore": CHORE,
                "completion": {
                    "id": 2,
                    "local_date": "2026-07-26",
                    "completed_at": "2026-07-26T12:00:00Z",
                    "timing": "on_time",
                    "points_awarded": 12,
                    "has_photo": False,
                },
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
    respx.get(f"{BASE}/api/v1/achievements").mock(
        return_value=httpx.Response(
            200,
            json={"points_balance": 0, "unlocked_count": 0, "achievements": []},
        )
    )
    try:
        assert client.get_home().total_count == 0
        assert client.get_confirm("qr-active-1").already_done is False
        result = client.complete_chore("qr-active-1", photo=b"x")
        assert result.points.total == 12
        assert client.get_achievements().unlocked_count == 0
    finally:
        client.close()


@pytest.mark.asyncio
async def test_sync_raises_inside_running_loop():
    client = SyncQrChoresClient(BASE, access_token="t")
    with pytest.raises(RuntimeError, match="running event loop"):
        client.get_me()
    # Avoid hang: don't call close via _run; close async client directly
    await client._async.aclose()


def test_sync_access_token_setter():
    client = SyncQrChoresClient(BASE)
    client.access_token = "abc"
    assert client.access_token == "abc"
    client.close()
