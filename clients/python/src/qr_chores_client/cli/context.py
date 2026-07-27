"""Typer context helpers."""

from __future__ import annotations

import typer

from qr_chores_client.cli.config import RuntimeConfig

# Typer context key for RuntimeConfig
CTX_KEY = "qrc_config"


def get_config(ctx: typer.Context) -> RuntimeConfig:
    cfg = ctx.ensure_object(dict).get(CTX_KEY)
    if cfg is None:
        raise RuntimeError("CLI config not initialized; call the root callback first")
    return cfg  # type: ignore[no-any-return]


def set_config(ctx: typer.Context, cfg: RuntimeConfig) -> None:
    ctx.ensure_object(dict)[CTX_KEY] = cfg
