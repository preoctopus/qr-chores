"""CLI integration tests against clients/mock-api (ASGI, no network).

Drives the full ``qrc`` Typer app through :func:`make_client` with an
httpx ASGI transport pointed at the deterministic mock server.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import (
    CHILD_EMAIL,
    CHILD_PASSWORD,
    PARENT_EMAIL,
    PARENT_PASSWORD,
    TINY_PNG,
)
from typer.testing import CliRunner

from qr_chores_client.cli.app import app

pytestmark = pytest.mark.integration

runner = CliRunner()


def _base(cli_mock_api: dict[str, Any]) -> list[str]:
    return ["--base-url", cli_mock_api["base_url"]]


def _login(cli_mock_api: dict[str, Any], email: str, password: str, *extra: str) -> Any:
    return runner.invoke(
        app,
        [*_base(cli_mock_api), *extra, "auth", "login", "-e", email, "-p", password],
    )


def test_cli_help_and_config_path(cli_mock_api: dict[str, Any]):
    help_r = runner.invoke(app, ["--help"])
    assert help_r.exit_code == 0
    assert "todays-chores" in help_r.output

    path_r = runner.invoke(app, [*_base(cli_mock_api), "config-path"])
    assert path_r.exit_code == 0
    assert "credentials.json" in path_r.output.replace("\n", "")


def test_unauthenticated_me(cli_mock_api: dict[str, Any]):
    r = runner.invoke(app, [*_base(cli_mock_api), "me"])
    assert r.exit_code == 3


def test_bad_login(cli_mock_api: dict[str, Any]):
    r = _login(cli_mock_api, "nope@example.com", "wrong")
    assert r.exit_code == 3


def test_parent_login_status_logout(cli_mock_api: dict[str, Any]):
    login = _login(cli_mock_api, PARENT_EMAIL, PARENT_PASSWORD)
    assert login.exit_code == 0, login.output
    assert "Parent" in login.output

    creds = Path(cli_mock_api["config_dir"]) / "credentials.json"
    assert creds.is_file()
    data = json.loads(creds.read_text())
    assert data["access_token"] == "parent-token"
    assert data["user"]["role"] == "parent"

    status = runner.invoke(app, [*_base(cli_mock_api), "auth", "status"])
    assert status.exit_code == 0
    assert "Parent" in status.output

    me = runner.invoke(app, [*_base(cli_mock_api), "--json", "me"])
    assert me.exit_code == 0
    payload = json.loads(me.output)
    assert payload["user"]["email"] == PARENT_EMAIL

    logout = runner.invoke(app, [*_base(cli_mock_api), "auth", "logout"])
    assert logout.exit_code == 0
    data = json.loads(creds.read_text())
    assert data["access_token"] is None

    me_after = runner.invoke(app, [*_base(cli_mock_api), "me"])
    assert me_after.exit_code == 3


def test_parent_todays_chores_and_history(cli_mock_api: dict[str, Any]):
    assert _login(cli_mock_api, PARENT_EMAIL, PARENT_PASSWORD).exit_code == 0

    today = runner.invoke(app, [*_base(cli_mock_api), "todays-chores"])
    assert today.exit_code == 0, today.output
    assert "Unload dishwasher" in today.output

    today_json = runner.invoke(app, [*_base(cli_mock_api), "--json", "today"])
    assert today_json.exit_code == 0
    body = json.loads(today_json.output)
    assert "board" in body
    assert any(item["chore"]["title"] == "Unload dishwasher" for item in body["board"])

    history = runner.invoke(app, [*_base(cli_mock_api), "history", "--limit", "10"])
    assert history.exit_code == 0
    # Seed completion for chore 1
    assert "Unload dishwasher" in history.output or "dishwasher" in history.output.lower()


def test_parent_chores_crud_and_qr(cli_mock_api: dict[str, Any], tmp_path: Path):
    assert _login(cli_mock_api, PARENT_EMAIL, PARENT_PASSWORD).exit_code == 0

    listed = runner.invoke(app, [*_base(cli_mock_api), "chores", "list"])
    assert listed.exit_code == 0
    assert "Unload dishwasher" in listed.output
    assert "Make bed" in listed.output

    get_one = runner.invoke(app, [*_base(cli_mock_api), "chores", "get", "1"])
    assert get_one.exit_code == 0
    assert "qr-active-1" in get_one.output or "Unload" in get_one.output

    create = runner.invoke(
        app,
        [
            *_base(cli_mock_api),
            "chores",
            "create",
            "--title",
            "Vacuum living room",
            "--base-points",
            "15",
            "--photo-policy",
            "optional",
            "--due-time",
            "18:00:00",
        ],
    )
    assert create.exit_code == 0, create.output
    assert "Vacuum living room" in create.output

    create_json = runner.invoke(
        app,
        [
            *_base(cli_mock_api),
            "--json",
            "chores",
            "create",
            "--title",
            "Take out trash",
            "--base-points",
            "8",
        ],
    )
    assert create_json.exit_code == 0
    created = json.loads(create_json.output)
    chore_id = created["id"]
    assert created["title"] == "Take out trash"

    update = runner.invoke(
        app,
        [*_base(cli_mock_api), "chores", "update", str(chore_id), "--base-points", "12"],
    )
    assert update.exit_code == 0
    assert "12" in update.output

    deactivate = runner.invoke(app, [*_base(cli_mock_api), "chores", "deactivate", str(chore_id)])
    assert deactivate.exit_code == 0
    assert "inactive" in deactivate.output.lower() or "Deactivated" in deactivate.output

    activate = runner.invoke(app, [*_base(cli_mock_api), "chores", "activate", str(chore_id)])
    assert activate.exit_code == 0

    qr = runner.invoke(app, [*_base(cli_mock_api), "chores", "qr", str(chore_id)])
    assert qr.exit_code == 0
    assert "qr" in qr.output.lower() or "QR" in qr.output

    png_path = tmp_path / "chore-qr.png"
    qr_png = runner.invoke(
        app,
        [*_base(cli_mock_api), "chores", "qr-png", str(chore_id), "-o", str(png_path)],
    )
    assert qr_png.exit_code == 0
    assert png_path.is_file()
    assert png_path.read_bytes()[:4] == b"\x89PNG" or len(png_path.read_bytes()) > 0

    delete = runner.invoke(app, [*_base(cli_mock_api), "chores", "delete", str(chore_id), "--yes"])
    assert delete.exit_code == 0

    missing = runner.invoke(app, [*_base(cli_mock_api), "chores", "get", str(chore_id)])
    assert missing.exit_code == 1


def test_parent_rewards(cli_mock_api: dict[str, Any]):
    assert _login(cli_mock_api, PARENT_EMAIL, PARENT_PASSWORD).exit_code == 0

    show = runner.invoke(app, [*_base(cli_mock_api), "rewards", "show"])
    assert show.exit_code == 0
    assert "Early bird" in show.output or "early" in show.output.lower()

    bonuses = runner.invoke(
        app,
        [
            *_base(cli_mock_api),
            "rewards",
            "bonuses",
            "--early",
            "7",
            "--on-time",
            "3",
            "--late",
            "1",
        ],
    )
    assert bonuses.exit_code == 0
    assert "7" in bonuses.output

    ach = runner.invoke(
        app,
        [
            *_base(cli_mock_api),
            "--json",
            "rewards",
            "achievement",
            "create",
            "--title",
            "Streak hero",
            "--criteria-type",
            "streak_days",
            "--threshold",
            "3",
            "--points-reward",
            "15",
        ],
    )
    assert ach.exit_code == 0, ach.output
    ach_body = json.loads(ach.output)
    ach_id = ach_body["id"]

    upd = runner.invoke(
        app,
        [
            *_base(cli_mock_api),
            "rewards",
            "achievement",
            "update",
            str(ach_id),
            "--title",
            "Streak master",
        ],
    )
    assert upd.exit_code == 0
    assert "Streak master" in upd.output

    toggle = runner.invoke(
        app, [*_base(cli_mock_api), "rewards", "achievement", "toggle", str(ach_id)]
    )
    assert toggle.exit_code == 0


def test_parent_forbidden_on_child_routes(cli_mock_api: dict[str, Any]):
    assert _login(cli_mock_api, PARENT_EMAIL, PARENT_PASSWORD).exit_code == 0

    home = runner.invoke(app, [*_base(cli_mock_api), "home"])
    assert home.exit_code == 4

    ach = runner.invoke(app, [*_base(cli_mock_api), "achievements"])
    assert ach.exit_code == 4


def test_child_home_confirm_complete_achievements(cli_mock_api: dict[str, Any], tmp_path: Path):
    assert _login(cli_mock_api, CHILD_EMAIL, CHILD_PASSWORD).exit_code == 0

    home = runner.invoke(app, [*_base(cli_mock_api), "home"])
    assert home.exit_code == 0, home.output
    assert "Unload dishwasher" in home.output or "Make bed" in home.output

    home_json = runner.invoke(app, [*_base(cli_mock_api), "--json", "home"])
    assert home_json.exit_code == 0
    home_body = json.loads(home_json.output)
    assert home_body["points_balance"] == 42

    # Already completed today in seed
    conf_done = runner.invoke(app, [*_base(cli_mock_api), "confirm", "qr-active-1"])
    assert conf_done.exit_code == 0
    assert "already" in conf_done.output.lower() or "Unload" in conf_done.output

    already = runner.invoke(app, [*_base(cli_mock_api), "complete", "qr-active-1"])
    assert already.exit_code == 0
    assert "Already" in already.output or "already" in already.output.lower()

    conf = runner.invoke(app, [*_base(cli_mock_api), "confirm", "qr-photo-required"])
    assert conf.exit_code == 0
    assert "Make bed" in conf.output

    # Photo required without photo → domain error
    no_photo = runner.invoke(app, [*_base(cli_mock_api), "complete", "qr-photo-required"])
    assert no_photo.exit_code == 1
    combined = (no_photo.output or "") + (no_photo.stderr or "")
    assert "photo" in combined.lower()

    photo = tmp_path / "proof.png"
    photo.write_bytes(TINY_PNG)
    done = runner.invoke(
        app,
        [
            *_base(cli_mock_api),
            "complete",
            "qr-photo-required",
            "--photo",
            str(photo),
        ],
    )
    assert done.exit_code == 0, done.output
    assert "Completed" in done.output or "pts" in done.output.lower()

    # Fetch proof photo for the seed completion (id=1 has photo)
    out = tmp_path / "seed-photo.bin"
    photo_get = runner.invoke(app, [*_base(cli_mock_api), "photo", "get", "1", "-o", str(out)])
    assert photo_get.exit_code == 0
    assert out.read_bytes() == TINY_PNG

    ach = runner.invoke(app, [*_base(cli_mock_api), "achievements"])
    assert ach.exit_code == 0
    assert "Early bird" in ach.output or "Achievement" in ach.output


def test_child_forbidden_on_parent_routes(cli_mock_api: dict[str, Any]):
    assert _login(cli_mock_api, CHILD_EMAIL, CHILD_PASSWORD).exit_code == 0

    today = runner.invoke(app, [*_base(cli_mock_api), "todays-chores"])
    assert today.exit_code == 4

    chores = runner.invoke(app, [*_base(cli_mock_api), "chores", "list"])
    assert chores.exit_code == 4


def test_parent_then_child_switch_accounts(cli_mock_api: dict[str, Any]):
    """Login as parent, then re-login as child overwrites credentials."""
    assert _login(cli_mock_api, PARENT_EMAIL, PARENT_PASSWORD).exit_code == 0
    assert runner.invoke(app, [*_base(cli_mock_api), "todays-chores"]).exit_code == 0

    assert _login(cli_mock_api, CHILD_EMAIL, CHILD_PASSWORD).exit_code == 0
    me = runner.invoke(app, [*_base(cli_mock_api), "--json", "me"])
    assert me.exit_code == 0
    assert json.loads(me.output)["user"]["role"] == "child"

    assert runner.invoke(app, [*_base(cli_mock_api), "home"]).exit_code == 0
    assert runner.invoke(app, [*_base(cli_mock_api), "todays-chores"]).exit_code == 4


def test_login_json_shape(cli_mock_api: dict[str, Any]):
    r = _login(cli_mock_api, PARENT_EMAIL, PARENT_PASSWORD, "--json")
    assert r.exit_code == 0, r.output
    body = json.loads(r.output)
    assert body["user"]["email"] == PARENT_EMAIL
    assert "credentials_path" in body
    assert body["token_type"] == "bearer"


def test_unknown_qr_token(cli_mock_api: dict[str, Any]):
    assert _login(cli_mock_api, CHILD_EMAIL, CHILD_PASSWORD).exit_code == 0
    r = runner.invoke(app, [*_base(cli_mock_api), "confirm", "no-such-token"])
    assert r.exit_code == 1


def test_photo_missing_completion(cli_mock_api: dict[str, Any], tmp_path: Path):
    assert _login(cli_mock_api, PARENT_EMAIL, PARENT_PASSWORD).exit_code == 0
    r = runner.invoke(
        app,
        [*_base(cli_mock_api), "photo", "get", "99999", "-o", str(tmp_path / "x.bin")],
    )
    assert r.exit_code == 1
