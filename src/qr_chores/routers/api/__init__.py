"""Internal JSON API under /api/v1 (native apps / integrations)."""

from fastapi import APIRouter

from qr_chores.routers.api import auth as api_auth
from qr_chores.routers.api import child as api_child

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(api_auth.router)
api_router.include_router(api_child.router)
