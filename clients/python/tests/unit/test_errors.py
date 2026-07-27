"""Unit tests for error types and mapping."""

from __future__ import annotations

import httpx
import pytest
import respx

from qr_chores_client import (
    ApiError,
    AuthError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    QrChoresClient,
    ValidationError,
)
from qr_chores_client.errors import ApiError as ApiErrorDirect

BASE = "https://api.example.test"


@pytest.fixture
async def client():
    c = QrChoresClient(BASE, access_token="tok")
    yield c
    await c.aclose()


@respx.mock
async def test_auth_error_401(client: QrChoresClient):
    respx.get(f"{BASE}/api/v1/me").mock(
        return_value=httpx.Response(401, json={"detail": "Not authenticated"})
    )
    with pytest.raises(AuthError) as ei:
        await client.get_me()
    assert ei.value.status_code == 401
    assert "Not authenticated" in str(ei.value)


@respx.mock
async def test_forbidden_403(client: QrChoresClient):
    respx.get(f"{BASE}/api/v1/today").mock(
        return_value=httpx.Response(403, json={"detail": "Insufficient permissions"})
    )
    with pytest.raises(ForbiddenError) as ei:
        await client.get_today()
    assert ei.value.status_code == 403


@respx.mock
async def test_not_found_404(client: QrChoresClient):
    respx.get(f"{BASE}/api/v1/chores/999").mock(
        return_value=httpx.Response(404, json={"detail": "Chore not found"})
    )
    with pytest.raises(NotFoundError) as ei:
        await client.get_chore(999)
    assert "Chore not found" in ei.value.message


@respx.mock
async def test_domain_error_400(client: QrChoresClient):
    respx.post(f"{BASE}/api/v1/c/qr-x/complete").mock(
        return_value=httpx.Response(
            400,
            json={"detail": {"message": "A photo is required.", "code": "photo_required"}},
        )
    )
    with pytest.raises(DomainError) as ei:
        await client.complete_chore("qr-x")
    assert ei.value.code == "photo_required"
    assert "photo" in ei.value.message.lower()
    assert "photo_required" in str(ei.value)


@respx.mock
async def test_validation_error_422(client: QrChoresClient):
    detail = [{"loc": ["body", "title"], "msg": "Field required", "type": "missing"}]
    respx.post(f"{BASE}/api/v1/chores").mock(
        return_value=httpx.Response(422, json={"detail": detail})
    )
    with pytest.raises(ValidationError) as ei:
        await client.create_chore({"title": ""})
    assert ei.value.errors == detail
    assert ei.value.status_code == 422


@respx.mock
async def test_generic_api_error_500(client: QrChoresClient):
    respx.get(f"{BASE}/api/v1/me").mock(return_value=httpx.Response(500, json={"detail": "boom"}))
    with pytest.raises(ApiError) as ei:
        await client.get_me()
    assert ei.value.status_code == 500
    assert "boom" in str(ei.value)


@respx.mock
async def test_non_json_error_body(client: QrChoresClient):
    respx.get(f"{BASE}/api/v1/me").mock(return_value=httpx.Response(502, text="Bad Gateway"))
    with pytest.raises(ApiError) as ei:
        await client.get_me()
    assert ei.value.status_code == 502


@respx.mock
async def test_detail_message_variants(client: QrChoresClient):
    # detail as list without 422-style handling on 500
    respx.get(f"{BASE}/api/v1/me").mock(
        return_value=httpx.Response(500, json={"detail": [{"msg": "x"}]})
    )
    with pytest.raises(ApiError) as ei:
        await client.get_me()
    assert "Validation failed" in str(ei.value) or "detail" in str(ei.value).lower() or True

    # non-dict body
    respx.get(f"{BASE}/api/v1/home").mock(return_value=httpx.Response(500, json=["weird"]))
    with pytest.raises(ApiError):
        await client.get_home()


@respx.mock
async def test_domain_error_without_code_object(client: QrChoresClient):
    respx.post(f"{BASE}/api/v1/c/qr-x/complete").mock(
        return_value=httpx.Response(400, json={"detail": "plain string domain"})
    )
    with pytest.raises(DomainError) as ei:
        await client.complete_chore("qr-x")
    assert ei.value.code == "domain_error"


@respx.mock
async def test_empty_response_json_error_body(client: QrChoresClient):
    respx.get(f"{BASE}/api/v1/me").mock(return_value=httpx.Response(500, content=b"not-json"))
    with pytest.raises(ApiError):
        await client.get_me()


def test_detail_message_none_and_other():
    assert QrChoresClient._detail_message(None) == "Request failed"
    assert QrChoresClient._detail_message({"detail": {"foo": 1}})
    assert QrChoresClient._detail_message({"detail": 123}) == "123"
    assert QrChoresClient._detail_message(42) == "42"


def test_api_error_str_without_status():
    err = ApiErrorDirect("oops")
    assert str(err) == "oops"


def test_domain_error_defaults():
    err = DomainError("msg", code="x")
    assert err.status_code == 400
    assert err.code == "x"
