"""Parent rewards / achievements admin."""

from __future__ import annotations

import typer

from qr_chores_client.cli import output
from qr_chores_client.cli.client_factory import make_client
from qr_chores_client.cli.context import get_config
from qr_chores_client.cli.errors import handle_api_errors
from qr_chores_client.models import AchievementCreate, AchievementUpdate

app = typer.Typer(
    name="rewards",
    help="Timing bonuses and achievements (parent).",
    no_args_is_help=True,
)

achievement_app = typer.Typer(
    name="achievement",
    help="Create, update, or toggle achievements.",
    no_args_is_help=True,
)
app.add_typer(achievement_app, name="achievement")


@app.command("show")
@handle_api_errors
def show(ctx: typer.Context) -> None:
    """Show bonuses + achievements (GET /api/v1/rewards)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        resp = client.get_rewards()
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(resp)
        return
    output.print_rewards(resp)


@app.command("bonuses")
@handle_api_errors
def bonuses(
    ctx: typer.Context,
    early: int = typer.Option(..., "--early", help="Early completion bonus points."),
    on_time: int = typer.Option(..., "--on-time", help="On-time bonus points."),
    late: int = typer.Option(
        ...,
        "--late",
        help="Late completion bonus points (negative allowed as a penalty).",
    ),
) -> None:
    """Replace timing bonuses (PUT /api/v1/rewards/bonuses)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        result = client.update_bonuses(
            early_bonus_points=early,
            on_time_bonus_points=on_time,
            late_bonus_points=late,
        )
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(result)
        return
    output.success(
        f"Bonuses set: early +{result.early_bonus_points}, "
        f"on-time +{result.on_time_bonus_points}, late {result.late_bonus_points:+d}"
    )


@achievement_app.command("create")
@handle_api_errors
def achievement_create(
    ctx: typer.Context,
    title: str = typer.Option(..., "--title", "-t"),
    criteria_type: str = typer.Option(
        ...,
        "--criteria-type",
        help=(
            "total_completions | complete_on_time_count | complete_early_count | "
            "photo_completions | streak_days"
        ),
    ),
    description: str = typer.Option("", "--description", "-d"),
    icon_key: str = typer.Option("star", "--icon-key"),
    threshold: int = typer.Option(1, "--threshold"),
    points_reward: int = typer.Option(0, "--points-reward"),
) -> None:
    """Create achievement (POST /api/v1/rewards/achievements)."""
    cfg = get_config(ctx)
    body = AchievementCreate(
        title=title,
        description=description,
        icon_key=icon_key,
        criteria_type=criteria_type,
        threshold=threshold,
        points_reward=points_reward,
    )
    client = make_client(cfg)
    try:
        ach = client.create_achievement(body)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(ach)
        return
    output.success(f"Created achievement id={ach.id}: {ach.title}")


@achievement_app.command("update")
@handle_api_errors
def achievement_update(
    ctx: typer.Context,
    achievement_id: int = typer.Argument(help="Achievement ID."),
    title: str | None = typer.Option(None, "--title", "-t"),
    description: str | None = typer.Option(None, "--description", "-d"),
    icon_key: str | None = typer.Option(None, "--icon-key"),
    criteria_type: str | None = typer.Option(None, "--criteria-type"),
    threshold: int | None = typer.Option(None, "--threshold"),
    points_reward: int | None = typer.Option(None, "--points-reward"),
) -> None:
    """Update achievement (PATCH /api/v1/rewards/achievements/{id})."""
    cfg = get_config(ctx)
    update = AchievementUpdate(
        title=title,
        description=description,
        icon_key=icon_key,
        criteria_type=criteria_type,
        threshold=threshold,
        points_reward=points_reward,
    )
    if not update.to_payload():
        output.error("No fields to update; pass at least one option")
        raise SystemExit(2)
    client = make_client(cfg)
    try:
        ach = client.update_achievement(achievement_id, update)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(ach)
        return
    output.success(f"Updated achievement id={ach.id}: {ach.title}")


@achievement_app.command("toggle")
@handle_api_errors
def achievement_toggle(
    ctx: typer.Context,
    achievement_id: int = typer.Argument(help="Achievement ID."),
) -> None:
    """Toggle achievement active flag (POST …/toggle)."""
    cfg = get_config(ctx)
    client = make_client(cfg)
    try:
        ach = client.toggle_achievement(achievement_id)
    finally:
        client.close()
    if cfg.as_json:
        output.emit_json(ach)
        return
    state = "active" if ach.is_active else "inactive"
    output.success(f"Achievement id={ach.id} is now {state}")
