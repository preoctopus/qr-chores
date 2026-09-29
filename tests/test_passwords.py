"""Password hashing unit tests."""

from qr_chores.auth.passwords import (
    hash_password,
    verify_password,
    verify_password_or_dummy,
)


def test_hash_and_verify_roundtrip() -> None:
    hashed = hash_password("s3cret!")
    assert hashed != "s3cret!"
    assert verify_password("s3cret!", hashed)
    assert not verify_password("wrong", hashed)


def test_different_hashes_for_same_password() -> None:
    a = hash_password("same")
    b = hash_password("same")
    assert a != b
    assert verify_password("same", a)
    assert verify_password("same", b)


def test_verify_password_or_dummy_matches_verify_password() -> None:
    hashed = hash_password("s3cret!")
    assert verify_password_or_dummy("s3cret!", hashed)
    assert not verify_password_or_dummy("wrong", hashed)


def test_verify_password_or_dummy_hashes_when_user_is_missing(monkeypatch) -> None:
    """A missing hash must still burn one verification (enumeration defence)."""
    from qr_chores.auth import passwords

    calls: list[str] = []
    real = passwords._password_hash

    class CountingHash:
        def verify(self, password: str, password_hash: str) -> bool:
            calls.append(password_hash)
            return real.verify(password, password_hash)

    monkeypatch.setattr(passwords, "_password_hash", CountingHash())

    assert verify_password_or_dummy("anything", None) is False
    assert calls == [passwords._DUMMY_HASH]
