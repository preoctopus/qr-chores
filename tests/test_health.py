"""Health endpoint tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_healthz_ok(client: AsyncClient) -> None:
    for path in ("/healthz", "/healthz/", "/health", "/health/"):
        response = await client.get(path)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
