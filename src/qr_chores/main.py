"""FastAPI application entrypoint."""

import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from qr_chores import __version__
from qr_chores.config import get_settings
from qr_chores.db import init_db
from qr_chores.logging_setup import (
    ERROR_LOGGER,
    RequestLoggingMiddleware,
    configure_logging,
)
from qr_chores.routers import auth, children, chores, complete, health, pages, photos, rewards
from qr_chores.routers.api import api_router
from qr_chores.templating import templates

# StaticFiles uses mimetypes; ensure web app manifests get the correct type.
mimetypes.add_type("application/manifest+json", ".webmanifest")

OPENAPI_TAGS = [
    {"name": "api-auth", "description": "Login, logout, and current user (`/api/v1`)."},
    {"name": "api-admin", "description": "Bootstrap user registration (`X-Admin-Key`)."},
    {"name": "api-child", "description": "Child home, QR confirm/complete, achievements."},
    {"name": "api-parent", "description": "Parent today board, history, children, and chore CRUD."},
    {"name": "api-rewards", "description": "Timing bonuses and achievement admin."},
    {"name": "api-photos", "description": "Authenticated completion photo download."},
    {"name": "auth", "description": "HTML session login/logout."},
    {"name": "pages", "description": "Server-rendered pages."},
    {"name": "chores", "description": "HTML parent chore management."},
    {"name": "rewards", "description": "HTML rewards admin."},
    {"name": "photos", "description": "HTML photo serving."},
    {"name": "health", "description": "Health checks."},
]

APP_DESCRIPTION = """\
Family chore app (HTML UI + internal JSON API).

**Internal API** (`/api/v1`): for native apps, automation, and MCP — not end-user docs.
See `docs/API.md` in the repo. Auth: `Authorization: Bearer <token>` from
`POST /api/v1/auth/login`, or the same session cookie as the HTML UI.

Production (`ENVIRONMENT=production`) disables interactive OpenAPI.
"""


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Configure logging early (console + optional SYSLOG_SERVER).
    configure_logging(get_settings())
    # Dev convenience: ensure tables exist. Production should use Alembic.
    await init_db()
    yield


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept


def _install_openapi(app: FastAPI) -> None:
    """Attach Bearer security scheme for /api/v1 interactive docs."""

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=OPENAPI_TAGS,
        )
        components = schema.setdefault("components", {})
        schemes = components.setdefault("securitySchemes", {})
        schemes["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "opaque",
            "description": (
                "Opaque access token from POST /api/v1/auth/login. "
                "Send as: Authorization: Bearer <access_token>"
            ),
        }
        # Mark /api/v1 routes (except login) as accepting Bearer by default in docs.
        for path, methods in schema.get("paths", {}).items():
            if not path.startswith("/api/v1"):
                continue
            for method, operation in methods.items():
                if method == "parameters" or not isinstance(operation, dict):
                    continue
                if path == "/api/v1/auth/login" and method == "post":
                    continue
                operation.setdefault("security", [{"BearerAuth": []}])
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def create_app() -> FastAPI:
    settings = get_settings()
    # Hide interactive API docs outside local development.
    docs_url = None if settings.is_production else "/docs"
    redoc_url = None if settings.is_production else "/redoc"
    openapi_url = None if settings.is_production else "/openapi.json"

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=APP_DESCRIPTION,
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        openapi_tags=OPENAPI_TAGS,
    )
    _install_openapi(app)

    # Request/action logging (mutations + authenticated traffic + HTTP errors).
    # Logging is also configured here so handlers work even before lifespan
    # (e.g. TestClient without full lifespan in some paths).
    configure_logging(settings)
    app.add_middleware(RequestLoggingMiddleware, settings=settings)

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(children.router)
    app.include_router(chores.router)
    app.include_router(complete.router)
    app.include_router(photos.router)
    app.include_router(rewards.router)
    app.include_router(api_router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """Catch-all: log unexpected exceptions, return safe error response.

        StarletteHTTPException is handled by the dedicated handler below (more
        specific type match); this only runs for true unexpected errors.
        """
        ERROR_LOGGER.exception(
            "unhandled path=%s method=%s: %s",
            request.url.path,
            request.method,
            exc,
        )
        if request.url.path == "/healthz" or request.url.path.startswith("/api/"):
            return JSONResponse(
                {"detail": "Internal server error"},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        if not _wants_html(request):
            return JSONResponse(
                {"detail": "Internal server error"},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "title": "Something went wrong",
                "message": "Please try again.",
                "status_code": 500,
                "primary_href": "/",
                "primary_label": "Go home",
                "user": None,
            },
            status_code=500,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code >= 500:
            ERROR_LOGGER.error(
                "http_exception path=%s method=%s status=%s detail=%s",
                request.url.path,
                request.method,
                exc.status_code,
                exc.detail,
            )
        elif exc.status_code >= 400 and exc.status_code not in (401, 404):
            # 401/404 are routine; still visible via request middleware for mutations
            ERROR_LOGGER.warning(
                "http_exception path=%s method=%s status=%s detail=%s",
                request.url.path,
                request.method,
                exc.status_code,
                exc.detail,
            )
        # Internal JSON API and healthz always return JSON (never HTML redirects).
        if request.url.path == "/healthz" or request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            if _wants_html(request):
                next_url = request.url.path
                if request.url.query:
                    next_url = f"{next_url}?{request.url.query}"
                return RedirectResponse(
                    f"/login?next={next_url}",
                    status_code=status.HTTP_303_SEE_OTHER,
                )
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

        if not _wants_html(request) and "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

        if exc.status_code == status.HTTP_403_FORBIDDEN:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Not allowed",
                    "message": "You don’t have permission to view this page.",
                    "status_code": 403,
                    "primary_href": "/",
                    "primary_label": "Go home",
                    "user": None,
                },
                status_code=403,
            )

        if exc.status_code == status.HTTP_404_NOT_FOUND:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Page not found",
                    "message": "That link doesn’t match anything here. Check the URL or head home.",
                    "status_code": 404,
                    "primary_href": "/",
                    "primary_label": "Go home",
                    "user": None,
                },
                status_code=404,
            )

        # Non-HTML clients: keep JSON
        if not _wants_html(request):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "title": "Something went wrong",
                "message": str(exc.detail) if exc.detail else "Please try again.",
                "status_code": exc.status_code,
                "primary_href": "/",
                "primary_label": "Go home",
                "user": None,
            },
            status_code=exc.status_code,
        )

    return app


app = create_app()


def run() -> None:
    import os

    import uvicorn

    port = int(os.environ.get("PORT", "8765"))
    uvicorn.run(
        "qr_chores.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    run()
