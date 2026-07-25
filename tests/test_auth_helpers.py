"""Unit tests for auth redirect helpers."""

from qr_chores.models.user import UserRole
from qr_chores.routers.auth import _home_for_role, _safe_next_url


def test_safe_next_url_empty() -> None:
    assert _safe_next_url(None) == "/"
    assert _safe_next_url("") == "/"


def test_safe_next_url_blocks_absolute() -> None:
    assert _safe_next_url("https://evil.example/phish") == "/"
    assert _safe_next_url("//evil.example") == "/"
    assert _safe_next_url("http://localhost/x") == "/"


def test_safe_next_url_allows_relative() -> None:
    assert _safe_next_url("/c/token") == "/c/token"
    assert _safe_next_url("/me/achievements") == "/me/achievements"


def test_safe_next_url_blocks_relative_without_slash() -> None:
    assert _safe_next_url("c/token") == "/"


def test_home_for_role() -> None:
    assert _home_for_role(UserRole.parent) == "/today"
    assert _home_for_role(UserRole.child) == "/home"
