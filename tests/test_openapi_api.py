"""OpenAPI polish checks for /api/v1 (non-production)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_openapi_includes_api_v1_and_bearer(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/home" in schema["paths"]
    assert "/api/v1/today" in schema["paths"]
    assert "/api/v1/chores" in schema["paths"]
    assert "/api/v1/rewards" in schema["paths"]
    assert "/api/v1/photos/{completion_id}" in schema["paths"]

    schemes = schema["components"]["securitySchemes"]
    assert "BearerAuth" in schemes
    assert schemes["BearerAuth"]["scheme"] == "bearer"

    # Protected route advertises Bearer in docs
    me = schema["paths"]["/api/v1/me"]["get"]
    assert any("BearerAuth" in (s or {}) for s in me.get("security", []))

    # Login remains public (no required security)
    login = schema["paths"]["/api/v1/auth/login"]["post"]
    assert "security" not in login or login.get("security") == []

    tag_names = {t["name"] for t in schema.get("tags", [])}
    assert "api-auth" in tag_names
    assert "api-parent" in tag_names
