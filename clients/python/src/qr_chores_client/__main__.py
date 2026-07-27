"""Entry point: python -m qr_chores_client → run FastMCP server."""

from __future__ import annotations


def main() -> None:
    from qr_chores_client.mcp_server import run

    run()


if __name__ == "__main__":
    main()
