"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from qr_chores import __version__
from qr_chores.config import get_settings
from qr_chores.db import init_db
from qr_chores.routers import auth, chores, complete, health, pages, photos, rewards
from qr_chores.templating import templates


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Dev convenience: ensure tables exist. Production should use Alembic.
    await init_db()
    yield


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(chores.router)
    app.include_router(complete.router)
    app.include_router(photos.router)
    app.include_router(rewards.router)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if request.url.path == "/healthz":
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
