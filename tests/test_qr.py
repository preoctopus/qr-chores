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


def test_chore_url_dynamic_request() -> None:
    from starlette.requests import Request

    settings = Settings(
        secret_key="test-secret-key",
        base_url="https://chores.example",
    )
    req_a = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/chores/1/qr",
            "headers": [
                (b"host", b"a.com"),
                (b"x-forwarded-proto", b"https"),
            ],
        }
    )
    assert chore_url(settings, "token1", request=req_a) == "https://a.com/c/token1"

    req_b = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/chores/1/qr",
            "headers": [
                (b"host", b"b.com:8080"),
                (b"x-forwarded-proto", b"http"),
            ],
        }
    )
    assert chore_url(settings, "token2", request=req_b) == "http://b.com:8080/c/token2"


def test_generate_qr_png_is_png() -> None:
    png = generate_qr_png("https://chores.example/c/token")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 100
