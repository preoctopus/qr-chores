"""Health check for Cloud Run."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
@router.get("/healthz/")
@router.get("/health")
@router.get("/health/")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
