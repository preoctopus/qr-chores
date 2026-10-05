"""Unit tests for the qrc CLI."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from qr_chores_client.cli.app import app
from qr_chores_client.cli.config import (
    DEFAULT_BASE_URL,
    Credentials,
    credentials_path,
    resolve_base_url,
    resolve_token,
)
from qr_chores_client.models import (
    AchievementAdmin,
    AchievementProgress,
    AchievementsResponse,
    BoardItem,
    Chore,
    ChoreConfirm,
    CompleteResponse,
    Completion,
    HomeResponse,
    PointsBreakdown,
    RewardsResponse,
    TimingBonuses,
    Unlock,
    User,
)

runner = CliRunner()

BASE = "https://api.example.test"

USER = User(
    id=1,
    email="dad@example.com",
    display_name="Dad",
    role="parent",
    points_balance=42,
)

CHILD = User(
    id=2,
    email="daughter@example.com",
    display_name="Daughter",
    role="child",
    points_balance=10,
)

CHORE = Chore(
    id=1,
    title="Unload dishwasher",
    description="Empty top first",
    qr_token="qr-active-1",
    due_time="20:00:00",
    schedule_days="0123456",
    photo_policy="optional",
    base_points=10,
    is_active=True,
)

COMPLETION = Completion(
    id=9,
    local_date="2026-07-27",
    completed_at="2026-07-27T19:00:00",
    timing="on_time",
    points_awarded=12,
    has_photo=True,
)

BOARD_ITEM = BoardItem(
    chore=CHORE,
    done=True,
    status_label="Done",
    status_kind="done",
    is_late_pending=False,
    timing="on_time",
    completion=COMPLETION,
)


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("QRC_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("QRC_BASE_URL", raising=False)
    monkeypatch.delenv("QR_CHORES_BASE_URL", raising=False)
    monkeypatch.delenv("QRC_TOKEN", raising=False)
    return tmp_path


def _save_token(config_dir: Path, user: User = USER, token: str = "test-token") -> None:
    creds = Credentials(
        base_url=BASE,
        access_token=token,
        user=user.model_dump(mode="json"),
    )
    creds.save(config_dir / "credentials.json")


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "todays-chores" in result.output
    assert "auth" in result.output
    assert "chores" in result.output
    assert "children" in result.output
    assert "qr_chores_client" in result.output


def test_auth_help():
    result = runner.invoke(app, ["auth", "--help"])
    assert result.exit_code == 0
    assert "login" in result.output
    assert "logout" in result.output


def test_chores_help():
    result = runner.invoke(app, ["chores", "--help"])
    assert result.exit_code == 0
    assert "create" in result.output
    assert "qr-png" in result.output


def test_children_help():
    result = runner.invoke(app, ["children", "--help"])
    assert result.exit_code == 0
    assert "create" in result.output
    assert "list" in result.output


def test_config_path(config_dir: Path):
    result = runner.invoke(app, ["config-path"])
    assert result.exit_code == 0
    # Rich may soft-wrap long paths; compare without whitespace.
    assert "credentials.json" in result.output.replace("\n", "")
    assert config_dir.name in result.output.replace("\n", "")


def test_unauthenticated_exits_3(config_dir: Path):
    result = runner.invoke(app, ["me"])
    assert result.exit_code == 3
    assert "Not authenticated" in result.output or "Not authenticated" in (result.stderr or "")


@respx.mock
def test_login_saves_credentials(config_dir: Path):
    respx.post(f"{BASE}/api/v1/auth/login").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "parent-token",
                "token_type": "bearer",
                "expires_in": 100,
                "user": USER.model_dump(mode="json"),
            },
        )
    )
    result = runner.invoke(
        app,
        [
            "--base-url",
            BASE,
            "auth",
            "login",
            "-e",
            "dad@example.com",
            "-p",
            "parent-pass",
        ],
    )
    assert result.exit_code == 0, result.output
    path = config_dir / "credentials.json"
    assert path.is_file()
    data = json.loads(path.read_text())
    assert data["access_token"] == "parent-token"
    assert data["user"]["email"] == "dad@example.com"
    assert "Logged in" in result.output


@respx.mock
def test_login_json(config_dir: Path):
    respx.post(f"{BASE}/api/v1/auth/login").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "t",
                "token_type": "bearer",
                "expires_in": 1,
                "user": USER.model_dump(mode="json"),
            },
        )
    )
    result = runner.invoke(
        app,
        [
            "--base-url",
            BASE,
            "--json",
            "auth",
            "login",
            "-e",
            "dad@example.com",
            "-p",
            "parent-pass",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["user"]["role"] == "parent"


@respx.mock
def test_me_and_todays_chores(config_dir: Path):
    _save_token(config_dir)
    respx.get(f"{BASE}/api/v1/me").mock(
        return_value=httpx.Response(200, json=USER.model_dump(mode="json"))
    )
    respx.get(f"{BASE}/api/v1/today").mock(
        return_value=httpx.Response(
            200,
            json={
                "local_date": "2026-07-27",
                "board": [BOARD_ITEM.model_dump(mode="json")],
            },
        )
    )

    me = runner.invoke(app, ["--base-url", BASE, "me"])
    assert me.exit_code == 0
    assert "Dad" in me.output

    today = runner.invoke(app, ["--base-url", BASE, "todays-chores"])
    assert today.exit_code == 0
    assert "Unload dishwasher" in today.output

    today_alias = runner.invoke(app, ["--base-url", BASE, "--json", "today"])
    assert today_alias.exit_code == 0
    body = json.loads(today_alias.output)
    assert body["local_date"] == "2026-07-27"


@respx.mock
def test_logout_clears_token(config_dir: Path):
    _save_token(config_dir)
    respx.post(f"{BASE}/api/v1/auth/logout").mock(return_value=httpx.Response(204))
    result = runner.invoke(app, ["--base-url", BASE, "auth", "logout"])
    assert result.exit_code == 0
    data = json.loads((config_dir / "credentials.json").read_text())
    assert data["access_token"] is None


@respx.mock
def test_chores_crud_flow(config_dir: Path):
    _save_token(config_dir)
    chore_json = CHORE.model_dump(mode="json")

    respx.get(f"{BASE}/api/v1/chores").mock(
        return_value=httpx.Response(200, json={"chores": [chore_json]})
    )
    respx.get(f"{BASE}/api/v1/chores/1").mock(return_value=httpx.Response(200, json=chore_json))
    respx.post(f"{BASE}/api/v1/chores").mock(return_value=httpx.Response(200, json=chore_json))
    respx.patch(f"{BASE}/api/v1/chores/1").mock(
        return_value=httpx.Response(200, json={**chore_json, "base_points": 15})
    )
    respx.post(f"{BASE}/api/v1/chores/1/activate").mock(
        return_value=httpx.Response(200, json=chore_json)
    )
    respx.post(f"{BASE}/api/v1/chores/1/deactivate").mock(
        return_value=httpx.Response(200, json={**chore_json, "is_active": False})
    )
    respx.delete(f"{BASE}/api/v1/chores/1").mock(
        return_value=httpx.Response(
            200,
            json={"deleted": True, "chore_id": 1, "completions_removed": 2},
        )
    )
    respx.get(f"{BASE}/api/v1/chores/1/qr").mock(
        return_value=httpx.Response(
            200,
            json={
                "chore_id": 1,
                "title": "Unload dishwasher",
                "qr_token": "qr-active-1",
                "qr_url": "https://example/c/qr-active-1",
                "png_path": "/api/v1/chores/1/qr.png",
            },
        )
    )
    respx.get(f"{BASE}/api/v1/chores/1/qr.png").mock(
        return_value=httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})
    )

    assert runner.invoke(app, ["--base-url", BASE, "chores", "list"]).exit_code == 0
    assert runner.invoke(app, ["--base-url", BASE, "chores", "get", "1"]).exit_code == 0
    create = runner.invoke(
        app,
        [
            "--base-url",
            BASE,
            "chores",
            "create",
            "--title",
            "Unload dishwasher",
            "--base-points",
            "10",
        ],
    )
    assert create.exit_code == 0, create.output
    update = runner.invoke(
        app,
        ["--base-url", BASE, "chores", "update", "1", "--base-points", "15"],
    )
    assert update.exit_code == 0
    assert runner.invoke(app, ["--base-url", BASE, "chores", "activate", "1"]).exit_code == 0
    assert runner.invoke(app, ["--base-url", BASE, "chores", "deactivate", "1"]).exit_code == 0
    assert runner.invoke(app, ["--base-url", BASE, "chores", "qr", "1"]).exit_code == 0

    out = config_dir / "qr.png"
    png = runner.invoke(
        app,
        ["--base-url", BASE, "chores", "qr-png", "1", "-o", str(out)],
    )
    assert png.exit_code == 0
    assert out.read_bytes().startswith(b"\x89PNG")

    delete = runner.invoke(app, ["--base-url", BASE, "chores", "delete", "1", "--yes"])
    assert delete.exit_code == 0


@respx.mock
def test_children_crud_flow(config_dir: Path):
    _save_token(config_dir)
    child_json = {
        "id": 3,
        "email": "sam@example.com",
        "first_name": "Sam",
        "last_name": "Kid",
        "display_name": "Sam Kid",
        "role": "child",
        "parent_id": 1,
        "is_active": True,
        "points_balance": 0,
    }
    respx.get(f"{BASE}/api/v1/children").mock(
        return_value=httpx.Response(200, json={"children": [child_json]})
    )
    respx.get(f"{BASE}/api/v1/children/3").mock(return_value=httpx.Response(200, json=child_json))
    respx.post(f"{BASE}/api/v1/children").mock(return_value=httpx.Response(201, json=child_json))
    respx.patch(f"{BASE}/api/v1/children/3").mock(
        return_value=httpx.Response(
            200,
            json={**child_json, "first_name": "Sammy", "display_name": "Sammy Kid"},
        )
    )
    respx.post(f"{BASE}/api/v1/children/3/activate").mock(
        return_value=httpx.Response(200, json=child_json)
    )
    respx.post(f"{BASE}/api/v1/children/3/deactivate").mock(
        return_value=httpx.Response(200, json={**child_json, "is_active": False})
    )

    listed = runner.invoke(app, ["--base-url", BASE, "children", "list"])
    assert listed.exit_code == 0
    assert "Sam Kid" in listed.output

    get_one = runner.invoke(app, ["--base-url", BASE, "children", "get", "3"])
    assert get_one.exit_code == 0

    create = runner.invoke(
        app,
        [
            "--base-url",
            BASE,
            "children",
            "create",
            "-e",
            "sam@example.com",
            "-p",
            "child-pass",
            "--first-name",
            "Sam",
            "--last-name",
            "Kid",
        ],
    )
    assert create.exit_code == 0, create.output
    assert "Created child" in create.output

    update = runner.invoke(
        app,
        ["--base-url", BASE, "children", "update", "3", "--first-name", "Sammy"],
    )
    assert update.exit_code == 0
    assert runner.invoke(app, ["--base-url", BASE, "children", "activate", "3"]).exit_code == 0
    assert runner.invoke(app, ["--base-url", BASE, "children", "deactivate", "3"]).exit_code == 0

    empty = runner.invoke(app, ["--base-url", BASE, "children", "update", "3"])
    assert empty.exit_code == 2

    json_list = runner.invoke(app, ["--base-url", BASE, "--json", "children", "list"])
    assert json_list.exit_code == 0
    payload = json.loads(json_list.output)
    assert payload["children"][0]["id"] == 3

    assert runner.invoke(app, ["--base-url", BASE, "--json", "children", "get", "3"]).exit_code == 0
    assert (
        runner.invoke(
            app,
            [
                "--base-url",
                BASE,
                "--json",
                "children",
                "create",
                "-e",
                "sam@example.com",
                "-p",
                "child-pass",
                "--first-name",
                "Sam",
                "--last-name",
                "Kid",
            ],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            ["--base-url", BASE, "--json", "children", "update", "3", "--first-name", "Sammy"],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(app, ["--base-url", BASE, "--json", "children", "activate", "3"]).exit_code
        == 0
    )
    assert (
        runner.invoke(app, ["--base-url", BASE, "--json", "children", "deactivate", "3"]).exit_code
        == 0
    )
    assert (
        runner.invoke(app, ["--base-url", BASE, "children", "list", "--active-only"]).exit_code == 0
    )


@respx.mock
def test_child_home_confirm_complete_achievements(config_dir: Path, tmp_path: Path):
    _save_token(config_dir, user=CHILD)
    home = HomeResponse(
        local_date="2026-07-27",
        points_balance=10,
        points_today=5,
        done_count=1,
        total_count=2,
        board=[BOARD_ITEM],
        recent_unlocks=[
            Unlock(
                id=1,
                title="Early bird",
                description="",
                icon_key="bird",
                points_reward=25,
            )
        ],
    )
    respx.get(f"{BASE}/api/v1/home").mock(
        return_value=httpx.Response(200, json=home.model_dump(mode="json"))
    )
    confirm = ChoreConfirm(
        chore=CHORE,
        scheduled_today=True,
        already_done=False,
        is_late_pending=False,
        completion=None,
    )
    respx.get(f"{BASE}/api/v1/c/qr-active-1").mock(
        return_value=httpx.Response(200, json=confirm.model_dump(mode="json"))
    )
    complete = CompleteResponse(
        already_done=False,
        chore=CHORE,
        completion=COMPLETION,
        points=PointsBreakdown(base=10, timing_bonus=2, achievement_points=0, total=12),
        unlocks=[],
    )
    respx.post(f"{BASE}/api/v1/c/qr-active-1/complete").mock(
        return_value=httpx.Response(200, json=complete.model_dump(mode="json"))
    )
    ach = AchievementsResponse(
        points_balance=10,
        unlocked_count=0,
        achievements=[
            AchievementProgress(
                id=1,
                title="Early bird",
                description="",
                icon_key="bird",
                criteria_type="complete_early_count",
                points_reward=25,
                unlocked=False,
                progress=1,
                threshold=5,
                percent=20,
            )
        ],
    )
    respx.get(f"{BASE}/api/v1/achievements").mock(
        return_value=httpx.Response(200, json=ach.model_dump(mode="json"))
    )

    assert runner.invoke(app, ["--base-url", BASE, "home"]).exit_code == 0
    assert runner.invoke(app, ["--base-url", BASE, "confirm", "qr-active-1"]).exit_code == 0
    photo = tmp_path / "proof.jpg"
    photo.write_bytes(b"fake-jpeg")
    done = runner.invoke(
        app,
        ["--base-url", BASE, "complete", "qr-active-1", "--photo", str(photo)],
    )
    assert done.exit_code == 0, done.output
    assert "Completed" in done.output
    assert runner.invoke(app, ["--base-url", BASE, "achievements"]).exit_code == 0


@respx.mock
def test_history_rewards_photo(config_dir: Path, tmp_path: Path):
    _save_token(config_dir)
    respx.get(url__regex=rf"{BASE}/api/v1/history.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "completion": COMPLETION.model_dump(mode="json"),
                        "chore_id": 1,
                        "chore_title": "Unload dishwasher",
                        "user_id": 2,
                    }
                ],
                "limit": 50,
            },
        )
    )
    rewards = RewardsResponse(
        bonuses=TimingBonuses(early_bonus_points=5, on_time_bonus_points=2, late_bonus_points=0),
        achievements=[
            AchievementAdmin(
                id=1,
                title="Early bird",
                description="",
                icon_key="bird",
                criteria_type="complete_early_count",
                threshold=5,
                points_reward=25,
                is_active=True,
            )
        ],
    )
    respx.get(f"{BASE}/api/v1/rewards").mock(
        return_value=httpx.Response(200, json=rewards.model_dump(mode="json"))
    )
    respx.put(f"{BASE}/api/v1/rewards/bonuses").mock(
        return_value=httpx.Response(
            200,
            json={
                "early_bonus_points": 5,
                "on_time_bonus_points": 2,
                "late_bonus_points": 0,
            },
        )
    )
    respx.post(f"{BASE}/api/v1/rewards/achievements").mock(
        return_value=httpx.Response(
            200,
            json=rewards.achievements[0].model_dump(mode="json"),
        )
    )
    respx.patch(f"{BASE}/api/v1/rewards/achievements/1").mock(
        return_value=httpx.Response(
            200,
            json=rewards.achievements[0].model_dump(mode="json"),
        )
    )
    respx.post(f"{BASE}/api/v1/rewards/achievements/1/toggle").mock(
        return_value=httpx.Response(
            200,
            json={**rewards.achievements[0].model_dump(mode="json"), "is_active": False},
        )
    )
    respx.get(f"{BASE}/api/v1/photos/9").mock(
        return_value=httpx.Response(200, content=b"img-bytes")
    )

    assert runner.invoke(app, ["--base-url", BASE, "history", "--limit", "10"]).exit_code == 0
    assert runner.invoke(app, ["--base-url", BASE, "rewards", "show"]).exit_code == 0
    assert (
        runner.invoke(
            app,
            [
                "--base-url",
                BASE,
                "rewards",
                "bonuses",
                "--early",
                "5",
                "--on-time",
                "2",
                "--late",
                "0",
            ],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            [
                "--base-url",
                BASE,
                "rewards",
                "achievement",
                "create",
                "--title",
                "Early bird",
                "--criteria-type",
                "complete_early_count",
                "--threshold",
                "5",
            ],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            [
                "--base-url",
                BASE,
                "rewards",
                "achievement",
                "update",
                "1",
                "--title",
                "Early bird",
            ],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(app, ["--base-url", BASE, "rewards", "achievement", "toggle", "1"]).exit_code
        == 0
    )
    out = tmp_path / "photo.bin"
    photo = runner.invoke(app, ["--base-url", BASE, "photo", "get", "9", "-o", str(out)])
    assert photo.exit_code == 0
    assert out.read_bytes() == b"img-bytes"


@respx.mock
def test_auth_error_exit_code(config_dir: Path):
    _save_token(config_dir)
    respx.get(f"{BASE}/api/v1/me").mock(
        return_value=httpx.Response(401, json={"detail": "Not authenticated"})
    )
    result = runner.invoke(app, ["--base-url", BASE, "me"])
    assert result.exit_code == 3


@respx.mock
def test_forbidden_exit_code(config_dir: Path):
    _save_token(config_dir)
    respx.get(f"{BASE}/api/v1/today").mock(
        return_value=httpx.Response(403, json={"detail": "Insufficient permissions"})
    )
    result = runner.invoke(app, ["--base-url", BASE, "todays-chores"])
    assert result.exit_code == 4


@respx.mock
def test_domain_error_on_complete(config_dir: Path):
    _save_token(config_dir, user=CHILD)
    respx.post(f"{BASE}/api/v1/c/qr-photo-required/complete").mock(
        return_value=httpx.Response(
            400,
            json={"detail": {"message": "Photo required", "code": "photo_required"}},
        )
    )
    result = runner.invoke(app, ["--base-url", BASE, "complete", "qr-photo-required"])
    assert result.exit_code == 1
    assert "photo_required" in result.output or "photo_required" in (result.stderr or "")


def test_resolve_base_url_priority(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QRC_BASE_URL", "https://from-env")
    assert resolve_base_url(None) == "https://from-env"
    assert resolve_base_url("https://cli") == "https://cli"
    monkeypatch.delenv("QRC_BASE_URL")
    creds = Credentials(base_url="https://stored")
    assert resolve_base_url(None, credentials=creds) == "https://stored"
    assert resolve_base_url(None, credentials=Credentials()) == DEFAULT_BASE_URL


def test_resolve_token_priority(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QRC_TOKEN", "env-token")
    assert resolve_token(None) == "env-token"
    assert resolve_token("cli-token") == "cli-token"
    monkeypatch.delenv("QRC_TOKEN")
    creds = Credentials(access_token="file-token")
    assert resolve_token(None, credentials=creds) == "file-token"


def test_credentials_corrupt_file(tmp_path: Path):
    path = tmp_path / "credentials.json"
    path.write_text("not-json", encoding="utf-8")
    c = Credentials.load(path)
    assert c.access_token is None


def test_credentials_path_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("QRC_CONFIG_DIR", raising=False)
    p = credentials_path()
    assert p.name == "credentials.json"


def test_update_chore_no_fields(config_dir: Path):
    _save_token(config_dir)
    result = runner.invoke(app, ["--base-url", BASE, "chores", "update", "1"])
    assert result.exit_code == 2


def test_photo_meta_types():
    from qr_chores_client.cli.app import _photo_meta

    assert _photo_meta(Path("a.png"))[1] == "image/png"
    assert _photo_meta(Path("a.webp"))[1] == "image/webp"
    assert _photo_meta(Path("a.jpg"))[1] == "image/jpeg"
    assert _photo_meta(Path("a.bin"))[1] == "image/jpeg"


@respx.mock
def test_token_flag_overrides_file(config_dir: Path):
    _save_token(config_dir, token="file-token")
    route = respx.get(f"{BASE}/api/v1/me").mock(
        return_value=httpx.Response(200, json=USER.model_dump(mode="json"))
    )
    result = runner.invoke(app, ["--base-url", BASE, "--token", "cli-token", "me"])
    assert result.exit_code == 0
    assert route.calls
    auth = route.calls.last.request.headers.get("authorization")
    assert auth == "Bearer cli-token"


@respx.mock
def test_todays_chores_grouped_and_history_days(config_dir: Path):
    _save_token(config_dir)
    board_item = BOARD_ITEM.model_dump(mode="json")
    respx.get(f"{BASE}/api/v1/today").mock(
        return_value=httpx.Response(
            200,
            json={
                "local_date": "2026-07-27",
                "board": [board_item],
                "summary": {
                    "total": 3,
                    "done": 1,
                    "pending": 1,
                    "overdue": 1,
                    "done_late": 1,
                    "points_today": 12,
                },
                "children": [
                    {
                        "child_id": 2,
                        "child_name": "Ava",
                        "done": 1,
                        "total": 3,
                        "overdue": 1,
                        "points_today": 12,
                        "items": [board_item],
                    }
                ],
            },
        )
    )
    day = {
        "local_date": "2026-07-26",
        "scheduled": 3,
        "done": 1,
        "missed_count": 1,
        "open_count": 1,
        "points": 12,
        "completions": [
            {
                "completion": {
                    "id": 1,
                    "local_date": "2026-07-26",
                    "completed_at": "2026-07-26T12:00:00Z",
                    "timing": "on_time",
                    "points_awarded": 12,
                    "has_photo": False,
                },
                "chore_id": 1,
                "chore_title": "Unload dishwasher",
                "user_id": 2,
            }
        ],
        "missed": [
            {"chore_id": 2, "chore_title": "Make bed", "user_id": 2, "due_time": "09:00:00"}
        ],
    }
    empty_day = {**day, "local_date": "2026-07-25", "scheduled": 0, "done": 0}
    empty_day.update(missed_count=0, open_count=0, points=0, completions=[], missed=[])
    days_route = respx.get(url__regex=rf"{BASE}/api/v1/history/days.*").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "start_date": "2026-07-25",
                    "end_date": "2026-07-26",
                    "days": [day, empty_day],
                },
            ),
            httpx.Response(
                200,
                json={"start_date": "2026-07-25", "end_date": "2026-07-25", "days": [empty_day]},
            ),
        ]
    )

    today = runner.invoke(app, ["--base-url", BASE, "todays-chores"])
    assert today.exit_code == 0, today.output
    assert "1/3 done" in today.output
    assert "overdue" in today.output
    assert "finished late" in today.output
    assert "Ava" in today.output

    days = runner.invoke(
        app, ["--base-url", BASE, "history-days", "--child-id", "2", "--timing", "late"]
    )
    assert days.exit_code == 0, days.output
    assert "Make bed" in days.output
    assert "1/3" in days.output
    assert days_route.calls[0].request.url.params["child_id"] == "2"

    empty = runner.invoke(app, ["--base-url", BASE, "history-days"])
    assert empty.exit_code == 0
    assert "Nothing scheduled" in empty.output
