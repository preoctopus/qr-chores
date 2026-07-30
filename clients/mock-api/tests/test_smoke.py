"""Smoke tests: every contract path responds."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from qr_chores_mock_api.app import app, reset_state
from qr_chores_mock_api.fixtures import CHILD_EMAIL, CHILD_PASSWORD, PARENT_EMAIL, PARENT_PASSWORD


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_state()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient, email: str, password: str) -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_auth_and_me(client: TestClient) -> None:
    token = _login(client, CHILD_EMAIL, CHILD_PASSWORD)
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["role"] == "child"
    r = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 204


def test_child_surface(client: TestClient) -> None:
    token = _login(client, CHILD_EMAIL, CHILD_PASSWORD)
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/home", headers=h).status_code == 200
    assert client.get("/api/v1/c/qr-active-1", headers=h).status_code == 200
    assert client.get("/api/v1/achievements", headers=h).status_code == 200
    # already done for chore 1 today
    r = client.post("/api/v1/c/qr-active-1/complete", headers=h)
    assert r.status_code == 200
    assert r.json()["already_done"] is True
    # photo required without photo
    r = client.post("/api/v1/c/qr-photo-required/complete", headers=h)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "photo_required"
    # with photo
    r = client.post(
        "/api/v1/c/qr-photo-required/complete",
        headers=h,
        files={"photo": ("p.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    assert r.status_code == 200
    assert r.json()["already_done"] is False


def test_parent_surface(client: TestClient) -> None:
    token = _login(client, PARENT_EMAIL, PARENT_PASSWORD)
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/today", headers=h).status_code == 200
    assert client.get("/api/v1/history", headers=h).status_code == 200
    kids = client.get("/api/v1/children", headers=h)
    assert kids.status_code == 200
    assert any(c["email"] == CHILD_EMAIL for c in kids.json()["children"])
    created_kid = client.post(
        "/api/v1/children",
        headers=h,
        json={
            "email": "newkid@example.com",
            "password": "kid-pass",
            "first_name": "New",
            "last_name": "Kid",
        },
    )
    assert created_kid.status_code == 201, created_kid.text
    kid_id = created_kid.json()["id"]
    assert created_kid.json()["parent_id"] == 1
    assert client.get(f"/api/v1/children/{kid_id}", headers=h).status_code == 200
    assert (
        client.patch(
            f"/api/v1/children/{kid_id}",
            headers=h,
            json={"first_name": "Newer"},
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/children/{kid_id}/deactivate", headers=h).status_code == 200
    assert client.post(f"/api/v1/children/{kid_id}/activate", headers=h).status_code == 200
    assert client.get("/api/v1/chores", headers=h).status_code == 200
    r = client.post(
        "/api/v1/chores",
        headers=h,
        json={
            "title": "New chore",
            "due_time": "18:00:00",
            "schedule_days": "0123456",
            "photo_policy": "none",
            "base_points": 3,
        },
    )
    assert r.status_code == 201
    cid = r.json()["id"]
    assert client.get(f"/api/v1/chores/{cid}", headers=h).status_code == 200
    assert client.patch(f"/api/v1/chores/{cid}", headers=h, json={"title": "Renamed"}).status_code == 200
    assert client.post(f"/api/v1/chores/{cid}/deactivate", headers=h).status_code == 200
    assert client.post(f"/api/v1/chores/{cid}/activate", headers=h).status_code == 200
    assert client.get(f"/api/v1/chores/{cid}/qr", headers=h).status_code == 200
    png = client.get(f"/api/v1/chores/{cid}/qr.png", headers=h)
    assert png.status_code == 200
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get("/api/v1/rewards", headers=h).status_code == 200
    assert (
        client.put(
            "/api/v1/rewards/bonuses",
            headers=h,
            json={"early_bonus_points": 1, "on_time_bonus_points": 1, "late_bonus_points": 0},
        ).status_code
        == 200
    )
    r = client.post(
        "/api/v1/rewards/achievements",
        headers=h,
        json={
            "title": "Streak",
            "criteria_type": "streak_days",
            "threshold": 3,
            "points_reward": 10,
        },
    )
    assert r.status_code == 201
    aid = r.json()["id"]
    assert client.patch(
        f"/api/v1/rewards/achievements/{aid}", headers=h, json={"title": "Streak 3"}
    ).status_code == 200
    assert client.post(f"/api/v1/rewards/achievements/{aid}/toggle", headers=h).status_code == 200
    photo = client.get("/api/v1/photos/1", headers=h)
    assert photo.status_code == 200
    assert client.delete(f"/api/v1/chores/{cid}", headers=h).status_code == 200


def test_role_guards(client: TestClient) -> None:
    child = _login(client, CHILD_EMAIL, CHILD_PASSWORD)
    parent = _login(client, PARENT_EMAIL, PARENT_PASSWORD)
    assert (
        client.get("/api/v1/today", headers={"Authorization": f"Bearer {child}"}).status_code
        == 403
    )
    assert (
        client.get("/api/v1/home", headers={"Authorization": f"Bearer {parent}"}).status_code
        == 403
    )
    assert client.get("/api/v1/me").status_code == 401
