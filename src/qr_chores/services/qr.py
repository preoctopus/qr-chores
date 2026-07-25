"""QR code generation for stable chore URLs."""

from io import BytesIO

import segno

from qr_chores.config import Settings


def chore_url(settings: Settings, qr_token: str) -> str:
    base = settings.base_url.rstrip("/")
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
