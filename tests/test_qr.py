"""QR generation tests."""

from qr_chores.config import Settings
from qr_chores.services.qr import chore_url, generate_qr_png, new_qr_token


def test_new_qr_token_unique() -> None:
    a = new_qr_token()
    b = new_qr_token()
    assert a != b
    assert len(a) >= 16


def test_chore_url() -> None:
    settings = Settings(
        secret_key="test-secret-key",
        base_url="https://chores.example",
    )
    assert chore_url(settings, "abc123") == "https://chores.example/c/abc123"


def test_generate_qr_png_is_png() -> None:
    png = generate_qr_png("https://chores.example/c/token")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 100
