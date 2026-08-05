"""In-process login rate limiter (brute-force protection)."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request

from qr_chores.config import Settings


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request headers or socket."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For can be a comma-separated list; first entry is the client IP.
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


class LoginRateLimiter:
    """Sliding-window in-process rate limiter keyed by (client_ip, email)."""

    def __init__(self) -> None:
        self._failures: dict[tuple[str, str], list[float]] = defaultdict(list)

    def _clean_old_attempts(self, key: tuple[str, str], now: float, window_seconds: int) -> None:
        cutoff = now - window_seconds
        self._failures[key] = [t for t in self._failures[key] if t > cutoff]
        if not self._failures[key]:
            self._failures.pop(key, None)

    def is_rate_limited(self, ip: str, email: str, settings: Settings) -> bool:
        """Check whether the (ip, email) combination is currently locked out."""
        key = (ip.strip(), email.strip().lower())
        now = time.time()
        self._clean_old_attempts(key, now, settings.login_rate_limit_window_seconds)
        attempts = len(self._failures.get(key, []))
        return attempts >= settings.login_rate_limit_attempts

    def record_failure(self, ip: str, email: str, settings: Settings) -> None:
        """Record a failed login attempt for the (ip, email) combination."""
        key = (ip.strip(), email.strip().lower())
        now = time.time()
        self._clean_old_attempts(key, now, settings.login_rate_limit_window_seconds)
        self._failures[key].append(now)

    def record_success(self, ip: str, email: str) -> None:
        """Clear failed attempts upon successful login."""
        key = (ip.strip(), email.strip().lower())
        self._failures.pop(key, None)

    def reset(self) -> None:
        """Clear all rate limit state (useful for tests)."""
        self._failures.clear()


_limiter = LoginRateLimiter()


def get_login_rate_limiter() -> LoginRateLimiter:
    return _limiter
