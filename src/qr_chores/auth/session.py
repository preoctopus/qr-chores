"""Signed session cookie helpers."""

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from qr_chores.config import Settings


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="qr-chores-session")


def dump_session(settings: Settings, user_id: int) -> str:
    return _serializer(settings).dumps({"uid": user_id})


def load_session(settings: Settings, token: str) -> int | None:
    try:
        data = _serializer(settings).loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid")
    if not isinstance(uid, int):
        return None
    return uid
