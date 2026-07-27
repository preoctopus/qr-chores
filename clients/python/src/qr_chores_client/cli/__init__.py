"""QR Chores terminal CLI (`qrc`).

Thin front-end over :class:`qr_chores_client.SyncQrChoresClient`.
"""

from __future__ import annotations

__all__ = ["main"]


def main() -> None:
    """Entry point for the ``qrc`` console script."""
    from qr_chores_client.cli.app import run

    run()
