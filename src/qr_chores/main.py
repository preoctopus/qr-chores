"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from qr_chores import __version__
from qr_chores.config import get_settings
from qr_chores.db import init_db
from qr_chores.routers import auth, chores, complete, health, pages, photos, rewards


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Dev convenience: ensure tables exist. Production should use Alembic.
    await init_db()
    yield


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

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    # Cloud Run sets PORT; local default 8765 (8000 often taken)
    import os

    port = int(os.environ.get("PORT", "8765"))
    uvicorn.run(
        "qr_chores.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    run()
