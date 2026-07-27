"""API error types for the QR Chores client."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """Base error for unexpected or unmapped API responses."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.body = body

    def __str__(self) -> str:
        if self.status_code is not None:
            return f"[{self.status_code}] {self.message}"
        return self.message


class AuthError(ApiError):
    """401 Unauthorized — missing/invalid credentials or bad login."""


class ForbiddenError(ApiError):
    """403 Forbidden — authenticated but wrong role."""


class NotFoundError(ApiError):
    """404 Not Found — unknown chore / QR / photo / achievement."""


class DomainError(ApiError):
    """400 Bad Request — domain rule failure (e.g. photo_required)."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        status_code: int = 400,
        body: Any = None,
    ) -> None:
        super().__init__(message, status_code=status_code, body=body)
        self.code = code

    def __str__(self) -> str:
        return f"[{self.status_code}] {self.code}: {self.message}"


class ValidationError(ApiError):
    """422 Unprocessable Entity — request validation failed."""

    def __init__(
        self,
        message: str = "Validation failed",
        *,
        errors: list[Any] | None = None,
        status_code: int = 422,
        body: Any = None,
    ) -> None:
        super().__init__(message, status_code=status_code, body=body)
        self.errors = errors or []
