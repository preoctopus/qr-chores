"""Internal JSON API under /api/v1 (native apps / integrations)."""

from fastapi import APIRouter

from qr_chores.routers.api import admin as api_admin
from qr_chores.routers.api import auth as api_auth
from qr_chores.routers.api import child as api_child
from qr_chores.routers.api import children as api_children
from qr_chores.routers.api import parent as api_parent
from qr_chores.routers.api import photos as api_photos
from qr_chores.routers.api import rewards as api_rewards

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(api_auth.router)
api_router.include_router(api_admin.router)
api_router.include_router(api_child.router)
api_router.include_router(api_children.router)
api_router.include_router(api_parent.router)
api_router.include_router(api_rewards.router)
api_router.include_router(api_photos.router)
