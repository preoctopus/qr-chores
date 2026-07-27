"""Rich console helpers, tables, and JSON output."""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Module-level consoles; reconfigured via ``configure_output``.
console = Console(stderr=False)
err_console = Console(stderr=True)


def configure_output(*, as_json: bool = False, no_color: bool = False) -> None:
    """Configure global consoles for this process."""
    global console, err_console
    force_no_color = (
        no_color or as_json or os.environ.get("NO_COLOR") is not None or not sys.stdout.isatty()
    )
    console = Console(stderr=False, force_terminal=not force_no_color, no_color=force_no_color)
    err_console = Console(stderr=True, force_terminal=not force_no_color, no_color=force_no_color)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)!r} is not JSON serializable")


def emit_json(data: Any) -> None:
    """Print JSON to stdout (for ``--json``)."""
    if isinstance(data, BaseModel):
        payload = data.model_dump(mode="json")
    elif isinstance(data, list) and data and isinstance(data[0], BaseModel):
        payload = [item.model_dump(mode="json") for item in data]
    else:
        payload = data
    sys.stdout.write(json.dumps(payload, indent=2, default=_json_default) + "\n")


def success(message: str) -> None:
    console.print(f"[bold green]✓[/] {message}")


def info(message: str) -> None:
    console.print(message)


def warn(message: str) -> None:
    err_console.print(f"[bold yellow]![/] {message}")


def error(message: str) -> None:
    err_console.print(f"[bold red]✗[/] {message}")


def role_style(role: str) -> str:
    r = (role or "").lower()
    if r == "parent":
        return "cyan"
    if r == "child":
        return "magenta"
    return "white"


def status_style(kind: str | None, label: str | None = None) -> str:
    k = (kind or label or "").lower()
    if k in ("done", "complete", "completed", "on_time", "early"):
        return "green"
    if k in ("late", "is_late", "late_pending"):
        return "red"
    if k in ("pending", "todo", "not_done"):
        return "yellow"
    return "white"


def print_user(user: Any, *, title: str = "Signed in") -> None:
    """Render a User model or dict."""
    if isinstance(user, BaseModel):
        data = user.model_dump(mode="json")
    else:
        data = dict(user)
    role = str(data.get("role", "?"))
    name = data.get("display_name") or data.get("email") or "?"
    email = data.get("email", "")
    points = data.get("points_balance", 0)
    style = role_style(role)
    panel = Panel(
        f"[bold]{name}[/]\n{email}\nRole: [{style}]{role}[/]  ·  Points: [bold]{points}[/]",
        title=title,
        border_style=style,
    )
    console.print(panel)


def print_board(
    board: list[Any],
    *,
    local_date: Any = None,
    title: str = "Today",
    extra_header: str | None = None,
) -> None:
    """Render a list of BoardItem-like objects."""
    date_s = str(local_date) if local_date is not None else ""
    header = title if not date_s else f"{title} · {date_s}"
    if extra_header:
        console.print(f"[bold]{header}[/]  {extra_header}")
    else:
        console.print(f"[bold]{header}[/]")

    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("Status", style="bold", min_width=10)
    table.add_column("Chore", min_width=16)
    table.add_column("Due", justify="right")
    table.add_column("Pts", justify="right")
    table.add_column("Timing")

    if not board:
        table.add_row("—", "[dim]No chores scheduled[/]", "—", "—", "—")
    else:
        for item in board:
            if isinstance(item, BaseModel):
                d = item.model_dump(mode="json")
            else:
                d = item
            chore = d.get("chore") or {}
            if isinstance(chore, BaseModel):
                chore = chore.model_dump(mode="json")
            label = str(d.get("status_label") or ("Done" if d.get("done") else "Pending"))
            kind = str(d.get("status_kind") or ("done" if d.get("done") else "pending"))
            st = status_style(kind, label)
            timing = d.get("timing") or "—"
            due = chore.get("due_time") or "—"
            if isinstance(due, str) and len(due) >= 5:
                due = due[:5]
            pts = chore.get("base_points", "—")
            title_s = chore.get("title") or "?"
            table.add_row(
                Text(label, style=st),
                title_s,
                str(due),
                str(pts),
                str(timing),
            )
    console.print(table)


def print_chore(chore: Any) -> None:
    if isinstance(chore, BaseModel):
        d = chore.model_dump(mode="json")
    else:
        d = dict(chore)
    active = d.get("is_active", True)
    badge = "[green]active[/]" if active else "[red]inactive[/]"
    console.print(
        Panel(
            f"[bold]{d.get('title')}[/]  (id={d.get('id')})  {badge}\n"
            f"{d.get('description') or '[dim]No description[/]'}\n"
            f"Due [cyan]{d.get('due_time')}[/]  ·  Days [cyan]{d.get('schedule_days')}[/]\n"
            f"Photo [cyan]{d.get('photo_policy')}[/]  ·  Base pts [bold]{d.get('base_points')}[/]\n"
            f"QR token: [dim]{d.get('qr_token')}[/]",
            title="Chore",
            border_style="blue",
        )
    )


def print_chores_table(chores: list[Any]) -> None:
    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("ID", justify="right")
    table.add_column("Title")
    table.add_column("Due", justify="right")
    table.add_column("Pts", justify="right")
    table.add_column("Photo")
    table.add_column("Active")
    for chore in chores:
        d = chore.model_dump(mode="json") if isinstance(chore, BaseModel) else dict(chore)
        due = d.get("due_time") or "—"
        if isinstance(due, str) and len(due) >= 5:
            due = due[:5]
        active = "yes" if d.get("is_active") else "[red]no[/]"
        table.add_row(
            str(d.get("id")),
            str(d.get("title")),
            str(due),
            str(d.get("base_points")),
            str(d.get("photo_policy")),
            active,
        )
    console.print(table)


def print_history(items: list[Any], *, limit: int | None = None) -> None:
    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("When")
    table.add_column("Chore")
    table.add_column("Timing")
    table.add_column("Pts", justify="right")
    table.add_column("Photo")
    for item in items:
        d = item.model_dump(mode="json") if isinstance(item, BaseModel) else dict(item)
        comp = d.get("completion") or {}
        if isinstance(comp, BaseModel):
            comp = comp.model_dump(mode="json")
        when = comp.get("completed_at") or comp.get("local_date") or "—"
        timing = comp.get("timing") or "—"
        pts = comp.get("points_awarded", "—")
        photo = "yes" if comp.get("has_photo") else "no"
        table.add_row(
            str(when)[:19],
            str(d.get("chore_title") or d.get("chore_id")),
            str(timing),
            str(pts),
            photo,
        )
    title = "History" if limit is None else f"History (limit={limit})"
    console.print(f"[bold]{title}[/]")
    console.print(table)


def print_achievements(resp: Any) -> None:
    d = resp.model_dump(mode="json") if isinstance(resp, BaseModel) else dict(resp)
    console.print(
        f"[bold]Achievements[/]  ·  unlocked {d.get('unlocked_count', 0)}  ·  "
        f"points [bold]{d.get('points_balance', 0)}[/]"
    )
    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("Status")
    table.add_column("Title")
    table.add_column("Progress", justify="right")
    table.add_column("Reward", justify="right")
    for a in d.get("achievements") or []:
        unlocked = a.get("unlocked")
        status = Text("UNLOCKED", style="green") if unlocked else Text("locked", style="dim")
        prog = f"{a.get('progress', 0)}/{a.get('threshold', 0)} ({a.get('percent', 0)}%)"
        table.add_row(
            status,
            str(a.get("title")),
            prog,
            str(a.get("points_reward", 0)),
        )
    console.print(table)


def print_rewards(resp: Any) -> None:
    d = resp.model_dump(mode="json") if isinstance(resp, BaseModel) else dict(resp)
    bonuses = d.get("bonuses") or {}
    console.print("[bold]Timing bonuses[/]")
    late = int(bonuses.get("late_bonus_points", 0) or 0)
    late_fmt = f"{late:+d}"
    console.print(
        f"  early [green]+{bonuses.get('early_bonus_points', 0)}[/]  ·  "
        f"on-time [cyan]+{bonuses.get('on_time_bonus_points', 0)}[/]  ·  "
        f"late [yellow]{late_fmt}[/]"
    )
    table = Table(show_header=True, header_style="bold", expand=True, title="Achievements (admin)")
    table.add_column("ID", justify="right")
    table.add_column("Title")
    table.add_column("Criteria")
    table.add_column("Threshold", justify="right")
    table.add_column("Reward", justify="right")
    table.add_column("Active")
    for a in d.get("achievements") or []:
        active = "yes" if a.get("is_active") else "[red]no[/]"
        table.add_row(
            str(a.get("id")),
            str(a.get("title")),
            f"{a.get('criteria_type')} ",
            str(a.get("threshold")),
            str(a.get("points_reward")),
            active,
        )
    console.print(table)


def print_complete(result: Any) -> None:
    d = result.model_dump(mode="json") if isinstance(result, BaseModel) else dict(result)
    chore = d.get("chore") or {}
    points = d.get("points") or {}
    if d.get("already_done"):
        warn(f"Already completed: {chore.get('title')}")
    else:
        success(f"Completed: {chore.get('title')}")
    console.print(
        f"  base [bold]{points.get('base', 0)}[/]  + timing "
        f"[bold]{points.get('timing_bonus', 0)}[/]  + achievements "
        f"[bold]{points.get('achievement_points', 0)}[/]  = "
        f"[bold green]{points.get('total', 0)}[/] pts"
    )
    for u in d.get("unlocks") or []:
        console.print(
            f"  [bold magenta]★ unlock[/] {u.get('title')} (+{u.get('points_reward', 0)} pts)"
        )


def print_confirm(confirm: Any) -> None:
    d = confirm.model_dump(mode="json") if isinstance(confirm, BaseModel) else dict(confirm)
    chore = d.get("chore") or {}
    flags = []
    if d.get("already_done"):
        flags.append("[yellow]already done today[/]")
    if d.get("is_late_pending"):
        flags.append("[red]late[/]")
    if not d.get("scheduled_today"):
        flags.append("[dim]not scheduled today[/]")
    flag_s = "  ·  ".join(flags) if flags else "[green]ready[/]"
    console.print(
        Panel(
            f"[bold]{chore.get('title')}[/]\n"
            f"Due {chore.get('due_time')}  ·  Photo {chore.get('photo_policy')}  ·  "
            f"{chore.get('base_points')} pts\n"
            f"{flag_s}",
            title="Confirm chore",
            border_style="magenta",
        )
    )


def print_qr_info(info: Any) -> None:
    d = info.model_dump(mode="json") if isinstance(info, BaseModel) else dict(info)
    console.print(
        Panel(
            f"[bold]{d.get('title')}[/] (chore {d.get('chore_id')})\n"
            f"Token: [cyan]{d.get('qr_token')}[/]\n"
            f"URL:   [link]{d.get('qr_url')}[/]\n"
            f"PNG:   {d.get('png_path')}",
            title="QR",
            border_style="blue",
        )
    )
