"""Security response headers middleware.

Adds baseline hardening headers to every HTTP response. The app has exactly
one script (`static/js/celebration.js`, loaded via `<script src>`) and no
inline scripts, so `script-src 'self'` costs nothing; inline `style="..."`
attributes are used throughout the templates, so style-src keeps
`'unsafe-inline'`. HSTS is only sent when the app is actually configured for
HTTPS (`settings.base_url` starts with `https://`) so local/dev over plain
HTTP never gets a browser-enforced upgrade.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from qr_chores.config import Settings, get_settings

_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

_STATIC_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"content-security-policy", _CSP.encode()),
]

_HSTS = (b"strict-transport-security", b"max-age=63072000; includeSubDomains")


class SecurityHeadersMiddleware:
    """Pure ASGI middleware: attach hardening headers to every HTTP response.

    Pure ASGI (not BaseHTTPMiddleware) so it stays cheap and safe under
    concurrent requests, matching the pattern used by RequestLoggingMiddleware.
    """

    def __init__(self, app: ASGIApp, settings: Settings | None = None) -> None:
        self.app = app
        self._settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = self._settings or get_settings()
        https = settings.base_url.startswith("https://")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(_STATIC_HEADERS)
                if https:
                    headers.append(_HSTS)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
