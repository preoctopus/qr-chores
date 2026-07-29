"""Typer application root for the ``qrc`` CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from qr_chores_client.cli import output
from qr_chores_client.cli.client_factory import make_client
from qr_chores_client.cli.commands import auth as auth_cmd
from qr_chores_client.cli.commands import chores as chores_cmd
from qr_chores_client.cli.commands import rewards as rewards_cmd
from qr_chores_client.cli.config import (
    DEFAULT_BASE_URL,
    Credentials,
    RuntimeConfig,
    credentials_path,
    resolve_base_url,
    resolve_token,
)
from qr_chores_client.cli.context import get_config, set_config
from qr_chores_client.cli.errors import handle_api_errors

EPILOG = f"""
[bold]API[/]
  Origin default: [cyan]{DEFAULT_BASE_URL}[/]
  Paths always under [cyan]/api/v1[/] (provided by the Python client library).

[bold]Auth[/]
  Tokens are stored under the platform config dir (see [cyan]qrc auth status[/]).
  Override with [cyan]--token[/] / [cyan]QRC_TOKEN[/], or [cyan]--base-url[/] /
  [cyan]QRC_BASE_URL[/] / [cyan]QR_CHORES_BASE_URL[/].

[bold]Roles[/]
  [cyan]parent[/] — todays-chores, chores, history, rewards
  [magenta]child[/]  — home, confirm, complete, achievements

[bold]Examples[/]
  qrc auth login -e dad@example.com -p parent-pass
  qrc todays-chores
  qrc chores list
  qrc chores create --title "Unload dishwasher" --base-points 10
  qrc auth login -e daughter@example.com -p child-pass
  qrc home
  qrc complete <qr_token> --photo proof.jpg
  qrc --json chores get 1

[bold]Full surface[/]
  Implements every method of the shared client contract (login through photos).
"""

app = typer.Typer(
    name="qrc",
    help=(
        "QR Chores command-line client.\n\n"
        "Talks to the family chore HTTP API via the typed "
        "[bold]qr_chores_client[/] library (no raw HTTP in this CLI)."
    ),
    epilog=EPILOG,
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)

app.add_typer(auth_cmd.app, name="auth")
app.add_typer(chores_cmd.app, name="chores")
app.add_typer(rewards_cmd.app, name="rewards")


@app.callback()
def main_callback(
    ctx: typer.Context,
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        envvar=["QRC_BASE_URL", "QR_CHORES_BASE_URL"],
        help=f"API origin (default: {DEFAULT_BASE_URL}). Paths use /api/v1.",
        show_default=False,
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        envvar="QRC_TOKEN",
        help="Bearer token override (else stored credentials).",
        show_default=False,
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON on stdout (disables color).",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable ANSI color (also respects NO_COLOR).",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="More detail on errors.",
    ),
) -> None:
    """Global options shared by all subcommands."""
    creds = Credentials.load()
    url = resolve_base_url(base_url, credentials=creds)
    access = resolve_token(token, credentials=creds)
    cfg = RuntimeConfig(
        base_url=url,
        access_token=access,
        as_json=as_json,
        no_color=no_color,
        verbose=verbose,
        credentials=creds,
    )
    set_config(ctx, cfg)
    output.configure_output(as_json=as_json, no_color=no_color)


@app.command("me")
@handle_api_errors
def me(ctx: typer.Context) -> None:
    """Show the authenticated user (GET /api/v1/me). Alias of [cyan]auth status[/]."""
    auth_cmd.status(ctx)


@app.command("todays-chores")
@handle_api_errors
def todays_chores(ctx: typer.Context) -> None:
    """Parent board for today (GET /api/v1/today)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        resp = client.get_today()
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(resp)
        return
    output.print_board(resp.board, local_date=resp.local_date, title="Today's chores")


@app.command("today")
@handle_api_errors
def today(ctx: typer.Context) -> None:
    """Alias for [cyan]todays-chores[/] (GET /api/v1/today)."""
    todays_chores(ctx)


@app.command("home")
@handle_api_errors
def home(ctx: typer.Context) -> None:
    """Child home: points + board (GET /api/v1/home)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        resp = client.get_home()
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(resp)
        return
    extra = (
        f"points [bold]{resp.points_balance}[/] "
        f"(+{resp.points_today} today)  ·  "
        f"done {resp.done_count}/{resp.total_count}"
    )
    output.print_board(
        resp.board,
        local_date=resp.local_date,
        title="Home",
        extra_header=extra,
    )
    if resp.recent_unlocks:
        output.console.print("[bold]Recent unlocks[/]")
        for u in resp.recent_unlocks:
            output.console.print(f"  [magenta]★[/] {u.title} (+{u.points_reward})")


@app.command("history")
@handle_api_errors
def history(
    ctx: typer.Context,
    child_id: int | None = typer.Option(None, "--child-id", help="Filter by child ID."),
    chore_id: int | None = typer.Option(None, "--chore-id", help="Filter by chore ID."),
    start_date: str | None = typer.Option(None, "--start-date", help="Start date (YYYY-MM-DD)."),
    end_date: str | None = typer.Option(None, "--end-date", help="End date (YYYY-MM-DD)."),
    timing: str | None = typer.Option(
        None, "--timing", help="Filter by timing (early, on_time, late)."
    ),
    page: int = typer.Option(1, "--page", "-p", min=1, help="Page number."),
    limit: int = typer.Option(50, "--limit", "-n", min=1, max=200, help="Max rows (1–200)."),
) -> None:
    """Recent completions with filtering and stats (GET /api/v1/history). Parent."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        resp = client.get_history(
            child_id=child_id,
            chore_id=chore_id,
            start_date=start_date,
            end_date=end_date,
            timing=timing,
            page=page,
            limit=limit,
        )
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(resp)
        return
    output.print_history(resp.items, limit=resp.limit)


@app.command("confirm")
@handle_api_errors
def confirm(
    ctx: typer.Context,
    qr_token: str = typer.Argument(help="QR token from the chore sticker / URL."),
) -> None:
    """Preview a chore before complete (GET /api/v1/c/{token}). Child."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        resp = client.get_confirm(qr_token)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(resp)
        return
    output.print_confirm(resp)


def _photo_meta(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        return path.name, "image/jpeg"
    if suffix == ".png":
        return path.name, "image/png"
    if suffix == ".webp":
        return path.name, "image/webp"
    return path.name, "image/jpeg"


@app.command("complete")
@handle_api_errors
def complete(
    ctx: typer.Context,
    qr_token: str = typer.Argument(help="QR token from the chore sticker / URL."),
    photo: Path | None = typer.Option(
        None,
        "--photo",
        help="Proof photo (JPEG / PNG / WebP). Required when photo_policy=required.",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    notes: str | None = typer.Option(
        None,
        "--notes",
        "-n",
        help="Optional note for parents (e.g. 'We are out of cat litter').",
    ),
) -> None:
    """Complete a chore (POST /api/v1/c/{token}/complete). Child."""
    cfg = get_config(ctx)
    photo_bytes: bytes | None = None
    filename = "photo.jpg"
    content_type = "image/jpeg"
    if photo is not None:
        photo_bytes = photo.read_bytes()
        filename, content_type = _photo_meta(photo)

    client = make_client(cfg)
    try:
        result = client.complete_chore(
            qr_token,
            photo=photo_bytes,
            photo_filename=filename,
            photo_content_type=content_type,
            notes=notes,
        )
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(result)
        return
    output.print_complete(result)


@app.command("achievements")
@handle_api_errors
def achievements(ctx: typer.Context) -> None:
    """Achievement progress for the child (GET /api/v1/achievements)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        resp = client.get_achievements()
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(resp)
        return
    output.print_achievements(resp)


photo_app = typer.Typer(
    name="photo",
    help="Download completion proof photos.",
    no_args_is_help=True,
)


@photo_app.command("get")
@handle_api_errors
def photo_get(
    ctx: typer.Context,
    completion_id: int = typer.Argument(help="Completion ID."),
    output_path: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="File path to write the image bytes.",
        dir_okay=False,
        writable=True,
    ),
) -> None:
    """Download a proof photo (GET /api/v1/photos/{completion_id})."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        data = client.get_photo(completion_id)
    finally:
        client.close()
    output_path.write_bytes(data)
    if cfg.as_json:
        output.emit_json(
            {
                "completion_id": completion_id,
                "path": str(output_path),
                "size": len(data),
            }
        )
        return
    output.success(f"Wrote {len(data)} bytes to {output_path}")


app.add_typer(photo_app, name="photo")


@app.command("config-path")
def config_path_cmd(ctx: typer.Context) -> None:
    """Print the path to the credentials file."""
    cfg = get_config(ctx)
    path = credentials_path()
    if cfg.as_json:
        output.emit_json({"path": str(path), "base_url": cfg.base_url})
        return
    output.info(str(path))


def run() -> None:
    """Console-script entry: ``qrc``."""
    app()


if __name__ == "__main__":
    run()
