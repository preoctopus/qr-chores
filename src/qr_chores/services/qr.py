"""QR code generation for stable chore URLs."""

from io import BytesIO
from typing import TYPE_CHECKING

import segno

from qr_chores.config import Settings

if TYPE_CHECKING:
    from starlette.requests import Request


def get_base_url_from_request(settings: Settings, request: "Request | None" = None) -> str:
    """Derive base URL dynamically from HTTP request headers (Host / X-Forwarded-*), falling back to settings."""
    if request is not None:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
        host = (
            request.headers.get("x-forwarded-host")
            or request.headers.get("host")
            or request.url.netloc
        )
        if host:
            host = host.split(",")[0].strip()
            return f"{proto}://{host}".rstrip("/")
    return settings.base_url.rstrip("/")


def chore_url(settings: Settings, qr_token: str, request: "Request | None" = None) -> str:
    base = get_base_url_from_request(settings, request)
    return f"{base}/c/{qr_token}"


def generate_qr_png(url: str, *, scale: int = 8) -> bytes:
    """High-contrast PNG with medium error correction for sticker wear."""
    qr = segno.make(url, error="m")
    buf = BytesIO()
    qr.save(buf, kind="png", scale=scale, border=2, dark="#000000", light="#ffffff")
    return buf.getvalue()


def new_qr_token() -> str:
    import secrets

    return secrets.token_urlsafe(16)
