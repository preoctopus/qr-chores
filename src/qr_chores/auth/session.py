"""Signed session cookie and API bearer token helpers."""

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from qr_chores.config import Settings

_SESSION_SALT = "qr-chores-session"
_API_SALT = "qr-chores-api"


def _serializer(settings: Settings, *, salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=salt)


def _load_uid(settings: Settings, token: str, *, salt: str) -> int | None:
    try:
        data = _serializer(settings, salt=salt).loads(
            token, max_age=settings.session_max_age_seconds
        )
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid")
    if not isinstance(uid, int):
        return None
    return uid


def dump_session(settings: Settings, user_id: int) -> str:
    """Signed cookie value for browser sessions."""
    return _serializer(settings, salt=_SESSION_SALT).dumps({"uid": user_id})


def load_session(settings: Settings, token: str) -> int | None:
    return _load_uid(settings, token, salt=_SESSION_SALT)


def dump_api_token(settings: Settings, user_id: int) -> str:
    """Opaque bearer token for /api/v1 clients (native apps, MCP, etc.)."""
    return _serializer(settings, salt=_API_SALT).dumps({"uid": user_id})


def load_api_token(settings: Settings, token: str) -> int | None:
    return _load_uid(settings, token, salt=_API_SALT)
