"""Password hashing helpers."""

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


# Hashed once at import so an unknown-email login pays the same argon2 cost as a
# known one. Without this, "no such user" returns ~30x faster than a wrong
# password, which is a usable account-enumeration oracle.
_DUMMY_HASH = hash_password("dummy-password-for-constant-time-login")


def verify_password_or_dummy(password: str, password_hash: str | None) -> bool:
    """Verify a password, burning an equivalent hash when the user is unknown.

    Always returns False for a missing hash, but takes the same wall-clock time
    as a failed verification against a real one.
    """
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, password_hash)
