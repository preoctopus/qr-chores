"""Synchronous thin wrapper around :class:`QrChoresClient`.

Uses a private event loop for the client lifetime so httpx connections
close cleanly after real HTTP (unlike one-shot ``asyncio.run`` per call).
Prefer the async client for concurrent workloads.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import httpx

from qr_chores_client.client import QrChoresClient
from qr_chores_client.models import (
    AchievementAdmin,
    AchievementCreate,
    AchievementsResponse,
    AchievementUpdate,
    ChildCreate,
    ChildListResponse,
    ChildUpdate,
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
    UndoCompletionResponse,
    User,
)


class SyncQrChoresClient:
    """Blocking façade over :class:`QrChoresClient`."""

    def __init__(
        self,
        base_url: str,
        *,
        access_token: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._async = QrChoresClient(
            base_url,
            access_token=access_token,
            timeout=timeout,
            transport=transport,
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    def _run[T](self, coro: Coroutine[Any, Any, T]) -> T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return self._ensure_loop().run_until_complete(coro)
        # Already in an event loop — do not nest; close the unused coroutine.
        coro.close()
        raise RuntimeError(
            "SyncQrChoresClient cannot be used from a running event loop; "
            "use QrChoresClient (async) instead."
        )

    def __enter__(self) -> SyncQrChoresClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            loop = self._ensure_loop()
            if not loop.is_closed():
                loop.run_until_complete(self._async.aclose())
        except RuntimeError:
            # Loop / transport already torn down.
            pass
        finally:
            if self._loop is not None and not self._loop.is_closed():
                self._loop.close()
            self._loop = None

    @property
    def access_token(self) -> str | None:
        return self._async.access_token

    @access_token.setter
    def access_token(self, value: str | None) -> None:
        self._async.access_token = value

    def set_access_token(self, token: str | None) -> None:
        self._async.set_access_token(token)

    def login(self, email: str, password: str) -> TokenResponse:
        return self._run(self._async.login(email, password))

    def logout(self) -> None:
        return self._run(self._async.logout())

    def get_me(self) -> User:
        return self._run(self._async.get_me())

    def get_home(self) -> HomeResponse:
        return self._run(self._async.get_home())

    def get_confirm(self, qr_token: str) -> ChoreConfirm:
        return self._run(self._async.get_confirm(qr_token))

    def complete_chore(
        self,
        qr_token: str,
        *,
        photo: bytes | None = None,
        photo_filename: str = "photo.jpg",
        photo_content_type: str = "image/jpeg",
        notes: str | None = None,
    ) -> CompleteResponse:
        return self._run(
            self._async.complete_chore(
                qr_token,
                photo=photo,
                photo_filename=photo_filename,
                photo_content_type=photo_content_type,
                notes=notes,
            )
        )

    def get_achievements(self) -> AchievementsResponse:
        return self._run(self._async.get_achievements())

    def get_today(self) -> TodayResponse:
        return self._run(self._async.get_today())

    def get_history(
        self,
        *,
        child_id: int | None = None,
        chore_id: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        timing: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> HistoryResponse:
        return self._run(
            self._async.get_history(
                child_id=child_id,
                chore_id=chore_id,
                start_date=start_date,
                end_date=end_date,
                timing=timing,
                page=page,
                limit=limit,
            )
        )

    def undo_completion(self, completion_id: int) -> UndoCompletionResponse:
        return self._run(self._async.undo_completion(completion_id))

    def list_children(self, *, include_inactive: bool = True) -> ChildListResponse:
        return self._run(self._async.list_children(include_inactive=include_inactive))

    def create_child(self, child: ChildCreate | dict[str, Any]) -> User:
        return self._run(self._async.create_child(child))

    def get_child(self, child_id: int) -> User:
        return self._run(self._async.get_child(child_id))

    def update_child(self, child_id: int, update: ChildUpdate | dict[str, Any]) -> User:
        return self._run(self._async.update_child(child_id, update))

    def activate_child(self, child_id: int) -> User:
        return self._run(self._async.activate_child(child_id))

    def deactivate_child(self, child_id: int) -> User:
        return self._run(self._async.deactivate_child(child_id))

    def list_chores(self, *, include_inactive: bool = True) -> ChoreListResponse:
        return self._run(self._async.list_chores(include_inactive=include_inactive))

    def create_chore(self, chore: ChoreCreate | dict[str, Any]) -> Chore:
        return self._run(self._async.create_chore(chore))

    def get_chore(self, chore_id: int) -> Chore:
        return self._run(self._async.get_chore(chore_id))

    def update_chore(self, chore_id: int, update: ChoreUpdate | dict[str, Any]) -> Chore:
        return self._run(self._async.update_chore(chore_id, update))

    def delete_chore(self, chore_id: int) -> ChoreDeleteResponse:
        return self._run(self._async.delete_chore(chore_id))

    def activate_chore(self, chore_id: int) -> Chore:
        return self._run(self._async.activate_chore(chore_id))

    def deactivate_chore(self, chore_id: int) -> Chore:
        return self._run(self._async.deactivate_chore(chore_id))

    def get_qr_info(self, chore_id: int) -> QrInfo:
        return self._run(self._async.get_qr_info(chore_id))

    def get_qr_png(self, chore_id: int) -> bytes:
        return self._run(self._async.get_qr_png(chore_id))

    def get_rewards(self) -> RewardsResponse:
        return self._run(self._async.get_rewards())

    def update_bonuses(
        self,
        *,
        early_bonus_points: int,
        on_time_bonus_points: int,
        late_bonus_points: int,
    ) -> TimingBonuses:
        return self._run(
            self._async.update_bonuses(
                early_bonus_points=early_bonus_points,
                on_time_bonus_points=on_time_bonus_points,
                late_bonus_points=late_bonus_points,
            )
        )

    def create_achievement(
        self,
        achievement: AchievementCreate | dict[str, Any],
    ) -> AchievementAdmin:
        return self._run(self._async.create_achievement(achievement))

    def update_achievement(
        self,
        achievement_id: int,
        update: AchievementUpdate | dict[str, Any],
    ) -> AchievementAdmin:
        return self._run(self._async.update_achievement(achievement_id, update))

    def toggle_achievement(self, achievement_id: int) -> AchievementAdmin:
        return self._run(self._async.toggle_achievement(achievement_id))

    def get_photo(self, completion_id: int) -> bytes:
        return self._run(self._async.get_photo(completion_id))
