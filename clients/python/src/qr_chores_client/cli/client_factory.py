"""Build :class:`SyncQrChoresClient` from runtime config."""

from __future__ import annotations

import httpx

from qr_chores_client.cli.config import RuntimeConfig
from qr_chores_client.sync_client import SyncQrChoresClient

# Tests may set this to an ASGI transport so ``qrc`` hits mock-api in-process.
_test_transport: httpx.AsyncBaseTransport | None = None


def set_test_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Install (or clear) an httpx transport used by :func:`make_client`."""
    global _test_transport
    _test_transport = transport


def make_client(cfg: RuntimeConfig, *, require_auth: bool = True) -> SyncQrChoresClient:
    """Return a sync client pointed at ``cfg.base_url``.

    Raises
    ------
    SystemExit
        With code 3 when ``require_auth`` is true and no token is available.
    """
    if require_auth and not cfg.access_token:
        from qr_chores_client.cli import output

        output.error("Not authenticated. Run: qrc auth login\n  or pass --token / set QRC_TOKEN")
        raise SystemExit(3)
    return SyncQrChoresClient(
        cfg.base_url,
        access_token=cfg.access_token,
        transport=_test_transport,
    )
