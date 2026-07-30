"""Parent children account management commands."""

from __future__ import annotations

import typer

from qr_chores_client.cli import output
from qr_chores_client.cli.client_factory import make_client
from qr_chores_client.cli.context import get_config
from qr_chores_client.cli.errors import handle_api_errors
from qr_chores_client.models import ChildCreate, ChildUpdate

app = typer.Typer(
    name="children",
    help="Manage children (parent). List, create, edit, activate/deactivate.",
    no_args_is_help=True,
)


@app.command("list")
@handle_api_errors
def list_children(
    ctx: typer.Context,
    active_only: bool = typer.Option(
        False,
        "--active-only",
        help="Omit inactive children (default: include inactive).",
    ),
) -> None:
    """List children (GET /api/v1/children)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        resp = client.list_children(include_inactive=not active_only)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(resp)
        return
    output.print_children_table(resp.children)


@app.command("get")
@handle_api_errors
def get_child(
    ctx: typer.Context,
    child_id: int = typer.Argument(help="Child user ID."),
) -> None:
    """Show one child (GET /api/v1/children/{id})."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        child = client.get_child(child_id)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(child)
        return
    output.print_user(child, title="Child")


@app.command("create")
@handle_api_errors
def create_child(
    ctx: typer.Context,
    email: str = typer.Option(..., "--email", "-e", help="Child username/email."),
    password: str = typer.Option(..., "--password", "-p", help="Initial password."),
    first_name: str = typer.Option(..., "--first-name", help="First name."),
    last_name: str = typer.Option(..., "--last-name", help="Last name."),
) -> None:
    """Create a child account (POST /api/v1/children)."""
    cfg = get_config(ctx)
    body = ChildCreate(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )
    client = make_client(cfg)
    try:
        child = client.create_child(body)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(child)
        return
    output.success(f"Created child {child.display_name} (id={child.id})")
    output.print_user(child, title="Child")


@app.command("update")
@handle_api_errors
def update_child(
    ctx: typer.Context,
    child_id: int = typer.Argument(help="Child user ID."),
    email: str | None = typer.Option(None, "--email", "-e"),
    password: str | None = typer.Option(None, "--password", "-p"),
    first_name: str | None = typer.Option(None, "--first-name"),
    last_name: str | None = typer.Option(None, "--last-name"),
    active: bool | None = typer.Option(
        None,
        "--active/--inactive",
        help="Set active flag (omit to leave unchanged).",
    ),
) -> None:
    """Partial update (PATCH /api/v1/children/{id})."""
    cfg = get_config(ctx)
    body = ChildUpdate(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        is_active=active,
    )
    if not body.to_payload():
        output.error("Provide at least one field to update.")
        raise SystemExit(2)
    client = make_client(cfg)
    try:
        child = client.update_child(child_id, body)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(child)
        return
    output.success(f"Updated child id={child.id}")
    output.print_user(child, title="Child")


@app.command("activate")
@handle_api_errors
def activate(
    ctx: typer.Context,
    child_id: int = typer.Argument(help="Child user ID."),
) -> None:
    """Activate a child account."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        child = client.activate_child(child_id)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(child)
        return
    output.success(f"Activated child id={child.id}")


@app.command("deactivate")
@handle_api_errors
def deactivate(
    ctx: typer.Context,
    child_id: int = typer.Argument(help="Child user ID."),
) -> None:
    """Deactivate a child account (keeps history)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        child = client.deactivate_child(child_id)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(child)
        return
    output.success(f"Deactivated child id={child.id}")
