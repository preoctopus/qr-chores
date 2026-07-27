"""Async HTTP client for QR Chores /api/v1."""

from __future__ import annotations

import json
from types import TracebackType
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from qr_chores_client.errors import (
    ApiError,
    AuthError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from qr_chores_client.models import (
    AchievementAdmin,
    AchievementCreate,
    AchievementsResponse,
    AchievementUpdate,
    Chore,
    ChoreConfirm,
    ChoreCreate,
    ChoreDeleteResponse,
    ChoreListResponse,
    ChoreUpdate,
    CompleteResponse,
    HistoryResponse,
    HomeResponse,
    QrInfo,
    RewardsResponse,
    TimingBonuses,
    TodayResponse,
    TokenResponse,
    User,
)

T = TypeVar("T", bound=BaseModel)

API_PREFIX = "/api/v1"


class QrChoresClient:
    """Async client for the QR Chores internal JSON API.

    Usage::

        async with QrChoresClient("http://localhost:8765") as client:
            await client.login("child@example.com", "child-pass")
            home = await client.get_home()
    """

    def __init__(
        self,
        base_url: str,
        *,
        access_token: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )

    async def __aenter__(self) -> QrChoresClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def set_access_token(self, token: str | None) -> None:
        self.access_token = token

    def _auth_headers(self) -> dict[str, str]:
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}

    @staticmethod
    def _detail_message(body: Any) -> str:
        if body is None:
            return "Request failed"
        if isinstance(body, dict):
            detail = body.get("detail", body)
            if isinstance(detail, str):
                return detail
            if isinstance(detail, dict):
                return str(detail.get("message") or detail)
            if isinstance(detail, list):
                return "Validation failed"
            return str(detail)
        return str(body)

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        status = response.status_code
        try:
            body: Any = response.json()
        except Exception:
            body = response.text

        message = self._detail_message(body)

        if status == 401:
            raise AuthError(message, status_code=status, body=body)
        if status == 403:
            raise ForbiddenError(message, status_code=status, body=body)
        if status == 404:
            raise NotFoundError(message, status_code=status, body=body)
        if status == 400:
            code = "domain_error"
            if isinstance(body, dict):
                detail = body.get("detail")
                if isinstance(detail, dict):
                    code = str(detail.get("code") or code)
                    message = str(detail.get("message") or message)
            raise DomainError(message, code=code, status_code=status, body=body)
        if status == 422:
            errors: list[Any] = []
            if isinstance(body, dict) and isinstance(body.get("detail"), list):
                errors = body["detail"]
            raise ValidationError(message, errors=errors, status_code=status, body=body)
        raise ApiError(message, status_code=status, body=body)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        files: Any = None,
        data: Any = None,
        expect_json: bool = True,
    ) -> Any:
        headers: dict[str, str] = {}
        if auth:
            headers.update(self._auth_headers())
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        response = await self._client.request(
            method,
            path,
            headers=headers,
            json=json_body,
            params=params,
            files=files,
            data=data,
        )
        self._raise_for_status(response)
        if response.status_code == 204 or not response.content:
            return None
        if not expect_json:
            return response.content
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type or response.content[:1] in (b"{", b"["):
            return response.json()
        return response.content

    async def _request_model(
        self,
        method: str,
        path: str,
        model: type[T],
        **kwargs: Any,
    ) -> T:
        data = await self._request(method, path, **kwargs)
        return model.model_validate(data)

    # --- Auth ---

    async def login(self, email: str, password: str) -> TokenResponse:
        data = await self._request(
            "POST",
            f"{API_PREFIX}/auth/login",
            auth=False,
            json_body={"email": email, "password": password},
        )
        token = TokenResponse.model_validate(data)
        self.access_token = token.access_token
        return token

    async def logout(self) -> None:
        """Clear local token. Server call is best-effort (matches Kotlin client)."""
        try:
            await self._request("POST", f"{API_PREFIX}/auth/logout")
        except ApiError:
            # 401/network/etc. still clear the client token.
            pass
        finally:
            self.access_token = None

    async def get_me(self) -> User:
        return await self._request_model("GET", f"{API_PREFIX}/me", User)

    # --- Child ---

    async def get_home(self) -> HomeResponse:
        return await self._request_model("GET", f"{API_PREFIX}/home", HomeResponse)

    async def get_confirm(self, qr_token: str) -> ChoreConfirm:
        return await self._request_model(
            "GET",
            f"{API_PREFIX}/c/{qr_token}",
            ChoreConfirm,
        )

    async def complete_chore(
        self,
        qr_token: str,
        *,
        photo: bytes | None = None,
        photo_filename: str = "photo.jpg",
        photo_content_type: str = "image/jpeg",
    ) -> CompleteResponse:
        files = None
        if photo is not None:
            files = {"photo": (photo_filename, photo, photo_content_type)}
        data = await self._request(
            "POST",
            f"{API_PREFIX}/c/{qr_token}/complete",
            files=files,
        )
        return CompleteResponse.model_validate(data)

    async def get_achievements(self) -> AchievementsResponse:
        return await self._request_model(
            "GET",
            f"{API_PREFIX}/achievements",
            AchievementsResponse,
        )

    # --- Parent board ---

    async def get_today(self) -> TodayResponse:
        return await self._request_model("GET", f"{API_PREFIX}/today", TodayResponse)

    async def get_history(self, *, limit: int = 50) -> HistoryResponse:
        return await self._request_model(
            "GET",
            f"{API_PREFIX}/history",
            HistoryResponse,
            params={"limit": limit},
        )

    # --- Chores ---

    async def list_chores(self, *, include_inactive: bool = True) -> ChoreListResponse:
        return await self._request_model(
            "GET",
            f"{API_PREFIX}/chores",
            ChoreListResponse,
            params={"include_inactive": include_inactive},
        )

    async def create_chore(self, chore: ChoreCreate | dict[str, Any]) -> Chore:
        payload = chore.model_dump() if isinstance(chore, ChoreCreate) else chore
        return await self._request_model(
            "POST",
            f"{API_PREFIX}/chores",
            Chore,
            json_body=payload,
        )

    async def get_chore(self, chore_id: int) -> Chore:
        return await self._request_model("GET", f"{API_PREFIX}/chores/{chore_id}", Chore)

    async def update_chore(
        self,
        chore_id: int,
        update: ChoreUpdate | dict[str, Any],
    ) -> Chore:
        if isinstance(update, ChoreUpdate):
            payload = update.to_payload()
        else:
            payload = update
        return await self._request_model(
            "PATCH",
            f"{API_PREFIX}/chores/{chore_id}",
            Chore,
            json_body=payload,
        )

    async def delete_chore(self, chore_id: int) -> ChoreDeleteResponse:
        return await self._request_model(
            "DELETE",
            f"{API_PREFIX}/chores/{chore_id}",
            ChoreDeleteResponse,
        )

    async def activate_chore(self, chore_id: int) -> Chore:
        return await self._request_model(
            "POST",
            f"{API_PREFIX}/chores/{chore_id}/activate",
            Chore,
        )

    async def deactivate_chore(self, chore_id: int) -> Chore:
        return await self._request_model(
            "POST",
            f"{API_PREFIX}/chores/{chore_id}/deactivate",
            Chore,
        )

    async def get_qr_info(self, chore_id: int) -> QrInfo:
        return await self._request_model(
            "GET",
            f"{API_PREFIX}/chores/{chore_id}/qr",
            QrInfo,
        )

    async def get_qr_png(self, chore_id: int) -> bytes:
        data = await self._request(
            "GET",
            f"{API_PREFIX}/chores/{chore_id}/qr.png",
            expect_json=False,
        )
        return bytes(data or b"")

    # --- Rewards ---

    async def get_rewards(self) -> RewardsResponse:
        return await self._request_model("GET", f"{API_PREFIX}/rewards", RewardsResponse)

    async def update_bonuses(
        self,
        *,
        early_bonus_points: int,
        on_time_bonus_points: int,
        late_bonus_points: int,
    ) -> TimingBonuses:
        return await self._request_model(
            "PUT",
            f"{API_PREFIX}/rewards/bonuses",
            TimingBonuses,
            json_body={
                "early_bonus_points": early_bonus_points,
                "on_time_bonus_points": on_time_bonus_points,
                "late_bonus_points": late_bonus_points,
            },
        )

    async def create_achievement(
        self,
        achievement: AchievementCreate | dict[str, Any],
    ) -> AchievementAdmin:
        payload = (
            achievement.model_dump() if isinstance(achievement, AchievementCreate) else achievement
        )
        return await self._request_model(
            "POST",
            f"{API_PREFIX}/rewards/achievements",
            AchievementAdmin,
            json_body=payload,
        )

    async def update_achievement(
        self,
        achievement_id: int,
        update: AchievementUpdate | dict[str, Any],
    ) -> AchievementAdmin:
        if isinstance(update, AchievementUpdate):
            payload = update.to_payload()
        else:
            payload = update
        return await self._request_model(
            "PATCH",
            f"{API_PREFIX}/rewards/achievements/{achievement_id}",
            AchievementAdmin,
            json_body=payload,
        )

    async def toggle_achievement(self, achievement_id: int) -> AchievementAdmin:
        return await self._request_model(
            "POST",
            f"{API_PREFIX}/rewards/achievements/{achievement_id}/toggle",
            AchievementAdmin,
        )

    # --- Photos ---

    async def get_photo(self, completion_id: int) -> bytes:
        data = await self._request(
            "GET",
            f"{API_PREFIX}/photos/{completion_id}",
            expect_json=False,
        )
        return bytes(data or b"")

    def model_dump_jsonable(self, model: BaseModel) -> dict[str, Any]:
        """Helper for MCP tools: dump a model to JSON-serializable dict."""
        return json.loads(model.model_dump_json())
