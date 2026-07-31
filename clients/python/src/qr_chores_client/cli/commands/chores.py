"""Parent chore CRUD + QR commands."""

from __future__ import annotations

from pathlib import Path

import typer

from qr_chores_client.cli import output
from qr_chores_client.cli.client_factory import make_client
from qr_chores_client.cli.context import get_config
from qr_chores_client.cli.errors import handle_api_errors
from qr_chores_client.models import ChoreCreate, ChoreUpdate

app = typer.Typer(
    name="chores",
    help="Manage chores (parent). List, create, edit, activate, QR codes.",
    no_args_is_help=True,
)


@app.command("list")
@handle_api_errors
def list_chores(
    ctx: typer.Context,
    active_only: bool = typer.Option(
        False,
        "--active-only",
        help="Omit inactive chores (default: include inactive).",
    ),
) -> None:
    """List chores (GET /api/v1/chores)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        resp = client.list_chores(include_inactive=not active_only)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(resp)
        return
    output.print_chores_table(resp.chores)


@app.command("get")
@handle_api_errors
def get_chore(
    ctx: typer.Context,
    chore_id: int = typer.Argument(help="Chore ID."),
) -> None:
    """Show one chore (GET /api/v1/chores/{id})."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        chore = client.get_chore(chore_id)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(chore)
        return
    output.print_chore(chore)


@app.command("create")
@handle_api_errors
def create_chore(
    ctx: typer.Context,
    title: str = typer.Option(..., "--title", "-t", help="Chore title."),
    description: str | None = typer.Option(None, "--description", "-d"),
    due_time: str = typer.Option("20:00:00", "--due-time", help="Local due time HH:MM[:SS]."),
    schedule_days: str = typer.Option(
        "0123456",
        "--schedule-days",
        help="Weekday digits 0=Mon … 6=Sun.",
    ),
    photo_policy: str = typer.Option(
        "none",
        "--photo-policy",
        help="required | optional | none",
    ),
    base_points: int = typer.Option(10, "--base-points", help="Points awarded on complete."),
    early_bonus: bool = typer.Option(
        True,
        "--early-bonus/--no-early-bonus",
        help="Whether completing early awards early bonus points.",
    ),
) -> None:
    """Create a chore (POST /api/v1/chores). Assigns a stable QR token."""
    cfg = get_config(ctx)
    body = ChoreCreate(
        title=title,
        description=description,
        due_time=due_time,
        schedule_days=schedule_days,
        photo_policy=photo_policy,
        base_points=base_points,
        early_bonus_enabled=early_bonus,
    )
    client = make_client(cfg)
    try:
        chore = client.create_chore(body)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(chore)
        return
    output.success(f"Created chore id={chore.id}")
    output.print_chore(chore)


@app.command("update")
@handle_api_errors
def update_chore(
    ctx: typer.Context,
    chore_id: int = typer.Argument(help="Chore ID."),
    title: str | None = typer.Option(None, "--title", "-t"),
    description: str | None = typer.Option(None, "--description", "-d"),
    due_time: str | None = typer.Option(None, "--due-time"),
    schedule_days: str | None = typer.Option(None, "--schedule-days"),
    photo_policy: str | None = typer.Option(None, "--photo-policy"),
    base_points: int | None = typer.Option(None, "--base-points"),
    early_bonus: bool | None = typer.Option(
        None,
        "--early-bonus/--no-early-bonus",
        help="Enable/disable early timing bonus.",
    ),
    clear_description: bool = typer.Option(
        False,
        "--clear-description",
        help="Clear description to null.",
    ),
) -> None:
    """Partial update (PATCH /api/v1/chores/{id})."""
    cfg = get_config(ctx)
    update = ChoreUpdate(
        title=title,
        description=description,
        due_time=due_time,
        schedule_days=schedule_days,
        photo_policy=photo_policy,
        base_points=base_points,
        early_bonus_enabled=early_bonus,
        clear_description=clear_description,
    )
    if not update.to_payload():
        output.error("No fields to update; pass at least one option")
        raise SystemExit(2)
    client = make_client(cfg)
    try:
        chore = client.update_chore(chore_id, update)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(chore)
        return
    output.success(f"Updated chore id={chore.id}")
    output.print_chore(chore)


@app.command("delete")
@handle_api_errors
def delete_chore(
    ctx: typer.Context,
    chore_id: int = typer.Argument(help="Chore ID."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Hard-delete chore, completions, and photos (DELETE /api/v1/chores/{id})."""
    if not yes:
        confirm = typer.confirm(
            f"Permanently delete chore {chore_id} and its history?",
            default=False,
        )
        if not confirm:
            output.warn("Aborted")
            raise SystemExit(0)
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        resp = client.delete_chore(chore_id)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(resp)
        return
    output.success(
        f"Deleted chore {resp.chore_id} ({resp.completions_removed} completions removed)"
    )


@app.command("activate")
@handle_api_errors
def activate(
    ctx: typer.Context,
    chore_id: int = typer.Argument(help="Chore ID."),
) -> None:
    """Re-activate a chore (POST /api/v1/chores/{id}/activate)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        chore = client.activate_chore(chore_id)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(chore)
        return
    output.success(f"Activated chore id={chore.id}")
    output.print_chore(chore)


@app.command("deactivate")
@handle_api_errors
def deactivate(
    ctx: typer.Context,
    chore_id: int = typer.Argument(help="Chore ID."),
) -> None:
    """Deactivate a chore without losing history (POST …/deactivate)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        chore = client.deactivate_chore(chore_id)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(chore)
        return
    output.success(f"Deactivated chore id={chore.id}")
    output.print_chore(chore)


@app.command("qr")
@handle_api_errors
def qr_info(
    ctx: typer.Context,
    chore_id: int = typer.Argument(help="Chore ID."),
) -> None:
    """Show QR metadata (GET /api/v1/chores/{id}/qr)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        info = client.get_qr_info(chore_id)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(info)
        return
    output.print_qr_info(info)


@app.command("qr-png")
@handle_api_errors
def qr_png(
    ctx: typer.Context,
    chore_id: int = typer.Argument(help="Chore ID."),
    output_path: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="File path to write the PNG.",
        dir_okay=False,
        writable=True,
    ),
) -> None:
    """Download QR PNG bytes (GET /api/v1/chores/{id}/qr.png)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        data = client.get_qr_png(chore_id)
    finally:
        client.close()
    output_path.write_bytes(data)
    if cfg.as_json:
        output.emit_json({"chore_id": chore_id, "path": str(output_path), "size": len(data)})
        return
    output.success(f"Wrote {len(data)} bytes to {output_path}")


@app.command("undo-completion")
@handle_api_errors
def undo_completion(
    ctx: typer.Context,
    completion_id: int = typer.Argument(help="Completion ID to undo."),
) -> None:
    """Undo a completion (POST /api/v1/completions/{id}/undo)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        res = client.undo_completion(completion_id)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(res)
        return
    output.success(f"Undid completion id={res.completion_id} (reverted {res.points_reverted} pts)")
