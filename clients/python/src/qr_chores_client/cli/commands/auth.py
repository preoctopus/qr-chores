"""Auth commands: login, logout, status."""

from __future__ import annotations

import getpass

import typer

from qr_chores_client.cli import output
from qr_chores_client.cli.client_factory import make_client
from qr_chores_client.cli.context import get_config
from qr_chores_client.cli.errors import handle_api_errors

app = typer.Typer(
    name="auth",
    help="Authenticate with the QR Chores API and manage stored credentials.",
    no_args_is_help=True,
)


@app.command("login")
@handle_api_errors
def login(
    ctx: typer.Context,
    email: str = typer.Option(
        ...,
        "--email",
        "-e",
        help="Account email (parent or child).",
        prompt=True,
    ),
    password: str | None = typer.Option(
        None,
        "--password",
        "-p",
        help="Account password (prompted if omitted).",
    ),
) -> None:
    """Log in and save a bearer token for later commands.

    Examples:

      qrc auth login -e dad@example.com -p parent-pass

      qrc auth login -e daughter@example.com
    """
    cfg = get_config(ctx)
    pw = password if password is not None else getpass.getpass("Password: ")
    if not pw:
        output.error("Password is required")
        raise SystemExit(2)

    client = make_client(cfg, require_auth=False)
    try:
        token = client.login(email, pw)
    finally:
        client.close()

    cfg.credentials.base_url = cfg.base_url
    cfg.credentials.access_token = token.access_token
    cfg.credentials.user = token.user.model_dump(mode="json")
    path = cfg.credentials.save()
    cfg.access_token = token.access_token

    if cfg.as_json:
        output.emit_json(
            {
                "user": token.user.model_dump(mode="json"),
                "expires_in": token.expires_in,
                "token_type": token.token_type,
                "credentials_path": str(path),
            }
        )
        return

    output.success(f"Logged in as {token.user.display_name} ({token.user.email})")
    output.print_user(token.user)
    output.info(f"[dim]Credentials saved to {path}[/]")


@app.command("logout")
@handle_api_errors
def logout(ctx: typer.Context) -> None:
    """Log out (clear local token; server logout is best-effort)."""
    cfg = get_config(ctx)
    if cfg.access_token:
        client = make_client(cfg, require_auth=False)
        try:
            client.logout()
        finally:
            client.close()
    path = cfg.credentials.clear_token()
    cfg.access_token = None
    if cfg.as_json:
        output.emit_json({"logged_out": True, "credentials_path": str(path)})
        return
    output.success("Logged out; local credentials cleared")


@app.command("status")
@handle_api_errors
def status(ctx: typer.Context) -> None:
    """Show current user (GET /api/v1/me) and credential store info."""
    cfg = get_config(ctx)
    client = make_client(cfg, require_auth=True)
    try:
        user = client.get_me()
    finally:
        client.close()

    if cfg.as_json:
        output.emit_json(
            {
                "user": user.model_dump(mode="json"),
                "base_url": cfg.base_url,
            }
        )
        return
    output.print_user(user, title="Current user")
    output.info(f"[dim]API: {cfg.base_url}[/]")
