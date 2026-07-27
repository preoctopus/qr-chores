"""Session cookie and API token signing tests."""

from qr_chores.auth.session import (
    dump_api_token,
    dump_session,
    load_api_token,
    load_session,
)
from qr_chores.config import Settings


def test_session_roundtrip() -> None:
    settings = Settings(secret_key="abc", session_max_age_seconds=3600)
    token = dump_session(settings, 42)
    assert load_session(settings, token) == 42


def test_session_rejects_tampered_token() -> None:
    settings = Settings(secret_key="abc", session_max_age_seconds=3600)
    token = dump_session(settings, 42)
    assert load_session(settings, token + "x") is None


def test_session_rejects_wrong_secret() -> None:
    a = Settings(secret_key="one", session_max_age_seconds=3600)
    b = Settings(secret_key="two", session_max_age_seconds=3600)
    token = dump_session(a, 7)
    assert load_session(b, token) is None


def test_api_token_roundtrip() -> None:
    settings = Settings(secret_key="abc", session_max_age_seconds=3600)
    token = dump_api_token(settings, 99)
    assert load_api_token(settings, token) == 99
    # Session and API salts must not be interchangeable
    assert load_session(settings, token) is None
    assert load_api_token(settings, dump_session(settings, 99)) is None
