"""Map library API errors to CLI exit codes and messages."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

import typer

from qr_chores_client.cli import output
from qr_chores_client.errors import (
    ApiError,
    AuthError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_FORBIDDEN = 4


def handle_api_errors[F: Callable[..., Any]](fn: F) -> F:
    """Decorator: catch library errors, print, exit with stable codes."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except typer.Exit:
            raise
        except SystemExit:
            raise
        except AuthError as exc:
            output.error(str(exc))
            raise SystemExit(EXIT_AUTH) from exc
        except ForbiddenError as exc:
            output.error(str(exc))
            raise SystemExit(EXIT_FORBIDDEN) from exc
        except NotFoundError as exc:
            output.error(str(exc))
            raise SystemExit(EXIT_ERROR) from exc
        except DomainError as exc:
            output.error(f"{exc.code}: {exc.message}")
            raise SystemExit(EXIT_ERROR) from exc
        except ValidationError as exc:
            output.error(str(exc))
            if exc.errors:
                for err in exc.errors:
                    output.err_console.print(f"  [dim]{err}[/]")
            raise SystemExit(EXIT_USAGE) from exc
        except ApiError as exc:
            output.error(str(exc))
            raise SystemExit(EXIT_ERROR) from exc
        except OSError as exc:
            output.error(f"I/O error: {exc}")
            raise SystemExit(EXIT_ERROR) from exc

    return wrapper  # type: ignore[return-value]
