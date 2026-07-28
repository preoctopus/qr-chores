"""Application logging configuration and request/action middleware.

Env (also on Settings):
  LOG_LEVEL       — DEBUG / INFO / WARNING / ERROR (default INFO)
  SYSLOG_SERVER   — host or host:port (UDP, default port 514). When set, logs
                    are also sent to that rsyslog/syslogd instance. Console
                    logging is always enabled for container platforms.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import time
from collections.abc import MutableMapping
from typing import Any

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from qr_chores.auth.session import load_api_token, load_session
from qr_chores.config import Settings, get_settings

# Dedicated loggers
APP_LOGGER = logging.getLogger("qr_chores")
ACTION_LOGGER = logging.getLogger("qr_chores.actions")
ERROR_LOGGER = logging.getLogger("qr_chores.errors")

_CONFIGURED = False

# Paths that are noise for action / access-style logs
_SKIP_PREFIXES = ("/static/", "/healthz", "/health", "/favicon.ico")
_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def parse_syslog_address(server: str) -> tuple[str, int] | None:
    """Parse ``host`` or ``host:port`` (optional udp:// / tcp:// prefix)."""
    raw = (server or "").strip()
    if not raw:
        return None
    for prefix in ("udp://", "tcp://", "syslog://"):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix) :]
            break
    if not raw:
        return None
    # host:port — last colon for host (IPv4 / hostname only; IPv6 use [addr]:port later)
    if raw.count(":") == 1:
        host, _, port_s = raw.partition(":")
        if not host or not port_s.isdigit():
            return None
        return host, int(port_s)
    if ":" in raw:
        # Ambiguous IPv6 without brackets — treat whole string as host, default port
        return raw, 514
    return raw, 514


def configure_logging(settings: Settings | None = None) -> None:
    """Idempotent logging setup for the FastAPI app process."""
    global _CONFIGURED
    if settings is None:
        settings = get_settings()

    level_name = (settings.log_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    # Allow reconfigure when level/syslog changes (tests); clear existing handlers once.
    if _CONFIGURED:
        root.handlers.clear()

    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    addr = parse_syslog_address(settings.syslog_server or "")
    if addr is not None:
        host, port = addr
        try:
            syslog = logging.handlers.SysLogHandler(
                address=(host, port),
                facility=logging.handlers.SysLogHandler.LOG_LOCAL0,
            )
            # RFC5424-ish tag prefix so rsyslog can filter by program
            syslog_formatter = logging.Formatter(
                "qr-chores[%(process)d]: %(levelname)s [%(name)s] %(message)s"
            )
            syslog.setLevel(level)
            syslog.setFormatter(syslog_formatter)
            root.addHandler(syslog)
            APP_LOGGER.info("Syslog handler enabled → %s:%s", host, port)
        except OSError as exc:
            APP_LOGGER.warning("Failed to attach SysLogHandler %s:%s: %s", host, port, exc)

    # Quiet noisy libraries a notch unless DEBUG
    if level > logging.DEBUG:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    _CONFIGURED = True
    APP_LOGGER.info(
        "Logging configured level=%s syslog=%s",
        level_name,
        settings.syslog_server or "off",
    )


def reset_logging_for_tests() -> None:
    """Clear configuration flag and handlers (tests only)."""
    global _CONFIGURED
    _CONFIGURED = False
    root = logging.getLogger()
    root.handlers.clear()


def _user_id_from_request(request: Request, settings: Settings) -> int | None:
    """Best-effort user id from Bearer or session cookie (no DB)."""
    auth = request.headers.get("Authorization")
    if auth:
        scheme, _, value = auth.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            uid = load_api_token(settings, value.strip())
            if uid is None:
                uid = load_session(settings, value.strip())
            if uid is not None:
                return uid
    cookie = request.cookies.get(settings.session_cookie_name)
    if cookie:
        return load_session(settings, cookie)
    return None


def _should_skip(path: str) -> bool:
    if path in ("/healthz", "/health") or path.startswith(("/healthz/", "/health/")):
        return True
    return any(path.startswith(prefix) for prefix in _SKIP_PREFIXES)


class RequestLoggingMiddleware:
    """Pure ASGI middleware: log user actions, HTTP errors, and unhandled exceptions.

    Uses pure ASGI (not BaseHTTPMiddleware) so concurrent requests stay safe under
    anyio task groups / race tests.
    """

    def __init__(self, app: ASGIApp, settings: Settings | None = None) -> None:
        self.app = app
        self._settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        method = (scope.get("method") or "GET").upper()
        if _should_skip(path):
            await self.app(scope, receive, send)
            return

        settings = self._settings or get_settings()
        request = Request(scope, receive=receive)
        start = time.perf_counter()
        user_id: int | None = None
        try:
            user_id = _user_id_from_request(request, settings)
        except Exception:  # noqa: BLE001 — never fail the request for logging
            user_id = None

        status_box: MutableMapping[str, Any] = {"code": 500}
        client_host = "-"
        if scope.get("client"):
            client_host = scope["client"][0]

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_box["code"] = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            ERROR_LOGGER.exception(
                "unhandled method=%s path=%s user_id=%s duration_ms=%.1f",
                method,
                path,
                user_id if user_id is not None else "-",
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        status = int(status_box["code"])

        if status >= 500:
            ERROR_LOGGER.error(
                "http_error method=%s path=%s status=%s user_id=%s client=%s duration_ms=%.1f",
                method,
                path,
                status,
                user_id if user_id is not None else "-",
                client_host,
                duration_ms,
            )
        elif status >= 400:
            ACTION_LOGGER.warning(
                "http_error method=%s path=%s status=%s user_id=%s client=%s duration_ms=%.1f",
                method,
                path,
                status,
                user_id if user_id is not None else "-",
                client_host,
                duration_ms,
            )
        elif method in _MUTATING or user_id is not None:
            ACTION_LOGGER.info(
                "action method=%s path=%s status=%s user_id=%s client=%s duration_ms=%.1f",
                method,
                path,
                status,
                user_id if user_id is not None else "-",
                client_host,
                duration_ms,
            )
        else:
            APP_LOGGER.debug(
                "request method=%s path=%s status=%s client=%s duration_ms=%.1f",
                method,
                path,
                status,
                client_host,
                duration_ms,
            )


def log_user_action(
    action: str,
    *,
    user_id: int | None = None,
    detail: str = "",
    **fields: object,
) -> None:
    """Explicit action log from route handlers (login, complete chore, etc.)."""
    parts = [f"event={action}"]
    if user_id is not None:
        parts.append(f"user_id={user_id}")
    if detail:
        parts.append(f"detail={detail}")
    for key, value in fields.items():
        parts.append(f"{key}={value}")
    ACTION_LOGGER.info(" ".join(parts))
