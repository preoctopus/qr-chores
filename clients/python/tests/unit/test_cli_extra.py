"""Extra CLI coverage: JSON paths, error codes, edge cases."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from qr_chores_client import cli as cli_pkg
from qr_chores_client.cli.app import app
from qr_chores_client.cli.config import Credentials
from qr_chores_client.cli.output import (
    _json_default,
    emit_json,
    print_board,
    print_complete,
    print_confirm,
    print_user,
    role_style,
    status_style,
    warn,
)
from qr_chores_client.models import User

runner = CliRunner()
BASE = "https://api.example.test"

USER = {
    "id": 1,
    "email": "dad@example.com",
    "display_name": "Dad",
    "role": "parent",
    "points_balance": 0,
}

CHORE = {
    "id": 1,
    "title": "Make bed",
    "description": None,
    "qr_token": "qr-1",
    "due_time": "09:00:00",
    "schedule_days": "0123456",
    "photo_policy": "none",
    "base_points": 5,
    "is_active": True,
}


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("QRC_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("QRC_BASE_URL", raising=False)
    monkeypatch.delenv("QR_CHORES_BASE_URL", raising=False)
    monkeypatch.delenv("QRC_TOKEN", raising=False)
    return tmp_path


def _save(config_dir: Path, token: str = "tok") -> None:
    Credentials(base_url=BASE, access_token=token, user=USER).save(config_dir / "credentials.json")


def test_cli_entry_main_invokes_app(monkeypatch: pytest.MonkeyPatch):
    called = {}

    def fake_run() -> None:
        called["ok"] = True

    monkeypatch.setattr("qr_chores_client.cli.app.run", fake_run)
    cli_pkg.main()
    assert called["ok"] is True


def test_role_and_status_styles():
    assert role_style("parent") == "cyan"
    assert role_style("child") == "magenta"
    assert role_style("other") == "white"
    assert status_style("done") == "green"
    assert status_style("late") == "red"
    assert status_style("pending") == "yellow"
    assert status_style("weird") == "white"
    assert status_style(None, "Done") == "green"


def test_json_default_and_emit(capsys: pytest.CaptureFixture[str]):
    from datetime import date, datetime, time

    assert _json_default(date(2026, 1, 1)) == "2026-01-01"
    assert _json_default(datetime(2026, 1, 1, 12, 0, 0)).startswith("2026")
    assert _json_default(time(12, 0)) == "12:00:00"
    with pytest.raises(TypeError):
        _json_default(object())
    emit_json([User.model_validate(USER)])
    out = capsys.readouterr().out
    assert "dad@example.com" in out
    emit_json({"a": 1})
    warn("heads up")


def test_print_helpers_edge_cases():
    print_user({"email": "x@y.z", "role": "child", "display_name": "X", "points_balance": 1})
    print_board([], local_date="2026-01-01", title="Empty")
    print_board(
        [
            {
                "chore": CHORE,
                "done": False,
                "status_label": "Pending",
                "status_kind": "pending",
                "is_late_pending": False,
                "timing": None,
            }
        ]
    )
    print_complete(
        {
            "already_done": True,
            "chore": CHORE,
            "completion": {},
            "points": {"base": 0, "timing_bonus": 0, "achievement_points": 0, "total": 0},
            "unlocks": [{"title": "X", "points_reward": 1}],
        }
    )
    print_confirm(
        {
            "chore": CHORE,
            "scheduled_today": False,
            "already_done": True,
            "is_late_pending": True,
            "completion": None,
        }
    )


@respx.mock
def test_json_paths_for_commands(config_dir: Path, tmp_path: Path):
    _save(config_dir)
    respx.get(f"{BASE}/api/v1/me").mock(return_value=httpx.Response(200, json=USER))
    respx.get(f"{BASE}/api/v1/chores").mock(
        return_value=httpx.Response(200, json={"chores": [CHORE]})
    )
    respx.get(f"{BASE}/api/v1/chores/1").mock(return_value=httpx.Response(200, json=CHORE))
    respx.post(f"{BASE}/api/v1/chores").mock(return_value=httpx.Response(200, json=CHORE))
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
                "title": "Make bed",
                "qr_token": "qr-1",
                "qr_url": "https://x/c/qr-1",
                "png_path": "/p",
            },
        )
    )
    respx.get(f"{BASE}/api/v1/chores/1/qr.png").mock(
        return_value=httpx.Response(200, content=b"png")
    )
    respx.get(f"{BASE}/api/v1/home").mock(
        return_value=httpx.Response(
            200,
            json={
                "local_date": "2026-07-27",
                "points_balance": 1,
                "points_today": 0,
                "done_count": 0,
                "total_count": 0,
                "board": [],
                "recent_unlocks": [],
            },
        )
    )
    respx.get(f"{BASE}/api/v1/c/qr-1").mock(
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
    respx.post(f"{BASE}/api/v1/c/qr-1/complete").mock(
        return_value=httpx.Response(
            200,
            json={
                "already_done": False,
                "chore": CHORE,
                "completion": {
                    "id": 1,
                    "local_date": "2026-07-27",
                    "completed_at": "2026-07-27T10:00:00",
                    "timing": "early",
                    "points_awarded": 5,
                    "has_photo": False,
                },
                "points": {
                    "base": 5,
                    "timing_bonus": 0,
                    "achievement_points": 0,
                    "total": 5,
                },
                "unlocks": [],
            },
        )
    )
    respx.get(f"{BASE}/api/v1/achievements").mock(
        return_value=httpx.Response(
            200,
            json={"points_balance": 1, "unlocked_count": 0, "achievements": []},
        )
    )
    respx.get(url__regex=rf"{BASE}/api/v1/history.*").mock(
        return_value=httpx.Response(200, json={"items": [], "limit": 50})
    )
    respx.get(f"{BASE}/api/v1/rewards").mock(
        return_value=httpx.Response(
            200,
            json={
                "bonuses": {
                    "early_bonus_points": 1,
                    "on_time_bonus_points": 1,
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
    ach = {
        "id": 1,
        "title": "A",
        "description": "",
        "icon_key": "star",
        "criteria_type": "streak_days",
        "threshold": 3,
        "points_reward": 10,
        "is_active": True,
    }
    respx.post(f"{BASE}/api/v1/rewards/achievements").mock(
        return_value=httpx.Response(200, json=ach)
    )
    respx.patch(f"{BASE}/api/v1/rewards/achievements/1").mock(
        return_value=httpx.Response(200, json=ach)
    )
    respx.post(f"{BASE}/api/v1/rewards/achievements/1/toggle").mock(
        return_value=httpx.Response(200, json={**ach, "is_active": False})
    )
    respx.get(f"{BASE}/api/v1/photos/1").mock(return_value=httpx.Response(200, content=b"xx"))
    respx.post(f"{BASE}/api/v1/auth/logout").mock(return_value=httpx.Response(204))

    cmds = [
        ["--json", "auth", "status"],
        ["--json", "chores", "list"],
        ["--json", "chores", "get", "1"],
        ["--json", "chores", "create", "--title", "Make bed"],
        ["--json", "chores", "update", "1", "--title", "Make bed"],
        ["--json", "chores", "activate", "1"],
        ["--json", "chores", "deactivate", "1"],
        ["--json", "chores", "delete", "1", "--yes"],
        ["--json", "chores", "qr", "1"],
        ["--json", "chores", "qr-png", "1", "-o", str(tmp_path / "q.png")],
        ["--json", "home"],
        ["--json", "confirm", "qr-1"],
        ["--json", "complete", "qr-1"],
        ["--json", "achievements"],
        ["--json", "history"],
        ["--json", "rewards", "show"],
        [
            "--json",
            "rewards",
            "bonuses",
            "--early",
            "1",
            "--on-time",
            "1",
            "--late",
            "0",
        ],
        [
            "--json",
            "rewards",
            "achievement",
            "create",
            "--title",
            "A",
            "--criteria-type",
            "streak_days",
        ],
        ["--json", "rewards", "achievement", "update", "1", "--title", "A"],
        ["--json", "rewards", "achievement", "toggle", "1"],
        ["--json", "photo", "get", "1", "-o", str(tmp_path / "p.bin")],
        ["--json", "config-path"],
        ["--json", "auth", "logout"],
    ]
    for cmd in cmds:
        result = runner.invoke(app, ["--base-url", BASE, *cmd])
        assert result.exit_code == 0, (cmd, result.output, result.exception)
        # valid JSON when using --json
        json.loads(result.output)


@respx.mock
def test_not_found_and_validation(config_dir: Path):
    _save(config_dir)
    respx.get(f"{BASE}/api/v1/chores/99").mock(
        return_value=httpx.Response(404, json={"detail": "Not found"})
    )
    r = runner.invoke(app, ["--base-url", BASE, "chores", "get", "99"])
    assert r.exit_code == 1

    respx.post(f"{BASE}/api/v1/chores").mock(
        return_value=httpx.Response(
            422,
            json={"detail": [{"loc": ["body", "title"], "msg": "field required"}]},
        )
    )
    r2 = runner.invoke(app, ["--base-url", BASE, "chores", "create", "--title", "x"])
    assert r2.exit_code == 2


@respx.mock
def test_api_error_generic(config_dir: Path):
    _save(config_dir)
    respx.get(f"{BASE}/api/v1/me").mock(return_value=httpx.Response(500, json={"detail": "boom"}))
    r = runner.invoke(app, ["--base-url", BASE, "me"])
    assert r.exit_code == 1


def test_delete_aborted(config_dir: Path):
    _save(config_dir)
    result = runner.invoke(app, ["--base-url", BASE, "chores", "delete", "1"], input="n\n")
    assert result.exit_code == 0
    assert "Aborted" in result.output


def test_login_empty_password(config_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "")
    result = runner.invoke(
        app,
        ["--base-url", BASE, "auth", "login", "-e", "dad@example.com"],
    )
    assert result.exit_code == 2


def test_logout_without_token(config_dir: Path):
    result = runner.invoke(app, ["--base-url", BASE, "auth", "logout"])
    assert result.exit_code == 0


def test_achievement_update_no_fields(config_dir: Path):
    _save(config_dir)
    result = runner.invoke(app, ["--base-url", BASE, "rewards", "achievement", "update", "1"])
    assert result.exit_code == 2


def test_credentials_non_dict(tmp_path: Path):
    path = tmp_path / "credentials.json"
    path.write_text("[]", encoding="utf-8")
    c = Credentials.load(path)
    assert c.access_token is None


def test_resolve_qr_chores_base_url(monkeypatch: pytest.MonkeyPatch):
    from qr_chores_client.cli.config import resolve_base_url

    monkeypatch.delenv("QRC_BASE_URL", raising=False)
    monkeypatch.setenv("QR_CHORES_BASE_URL", "https://legacy")
    assert resolve_base_url(None) == "https://legacy"


def test_get_config_missing():
    from click import Command, Context

    from qr_chores_client.cli.context import get_config

    ctx = Context(Command("x"))
    with pytest.raises(RuntimeError):
        get_config(ctx)


@respx.mock
def test_io_error_on_photo_write(config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _save(config_dir)
    respx.get(f"{BASE}/api/v1/photos/1").mock(return_value=httpx.Response(200, content=b"data"))

    def boom(self: Path, data: bytes) -> int:  # noqa: ARG001
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", boom)
    r = runner.invoke(app, ["--base-url", BASE, "photo", "get", "1", "-o", str(tmp_path / "x")])
    assert r.exit_code == 1
