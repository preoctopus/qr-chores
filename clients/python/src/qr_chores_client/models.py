"""Pydantic models matching QR Chores /api/v1 JSON (snake_case)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    email: str
    display_name: str
    role: str
    points_balance: int = 0


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User


class Chore(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    title: str
    description: str | None = None
    qr_token: str
    due_time: time | str
    schedule_days: str
    photo_policy: str
    base_points: int
    early_bonus_enabled: bool = True
    is_active: bool


class Completion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    local_date: date | str
    completed_at: datetime | str
    timing: str
    points_awarded: int
    has_photo: bool


class BoardItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chore: Chore
    done: bool
    status_label: str
    status_kind: str
    is_late_pending: bool
    timing: str | None = None
    completion: Completion | None = None


class Unlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    title: str
    description: str | None = None
    icon_key: str
    points_reward: int
    unlocked_at: datetime | str | None = None


class HomeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    local_date: date | str
    points_balance: int
    points_today: int
    done_count: int
    total_count: int
    board: list[BoardItem]
    recent_unlocks: list[Unlock] = Field(default_factory=list)


class ChoreConfirm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chore: Chore
    scheduled_today: bool
    already_done: bool
    is_late_pending: bool
    completion: Completion | None = None


class PointsBreakdown(BaseModel):
    model_config = ConfigDict(extra="ignore")

    base: int
    timing_bonus: int
    achievement_points: int
    total: int


class CompleteResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    already_done: bool
    chore: Chore
    completion: Completion
    points: PointsBreakdown
    unlocks: list[Unlock] = Field(default_factory=list)


class AchievementProgress(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    title: str
    description: str | None = None
    icon_key: str
    criteria_type: str
    points_reward: int
    unlocked: bool
    progress: int
    threshold: int
    percent: int


class AchievementsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    points_balance: int
    unlocked_count: int
    achievements: list[AchievementProgress]


class TodayResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    local_date: date | str
    board: list[BoardItem]


class HistoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    completion: Completion
    chore_id: int
    chore_title: str
    user_id: int


class HistoryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[HistoryItem]
    limit: int


class ChoreListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chores: list[Chore]


class ChoreCreate(BaseModel):
    """Body for POST /api/v1/chores."""

    title: str
    description: str | None = None
    due_time: str = "20:00:00"
    schedule_days: str = "0123456"
    photo_policy: str = "none"
    base_points: int = 10
    early_bonus_enabled: bool = True


class ChoreUpdate(BaseModel):
    """Body for PATCH /api/v1/chores/{id} (partial)."""

    title: str | None = None
    description: str | None = None
    due_time: str | None = None
    schedule_days: str | None = None
    photo_policy: str | None = None
    base_points: int | None = None
    early_bonus_enabled: bool | None = None
    clear_description: bool = False

    def to_payload(self) -> dict[str, Any]:
        """Serialize omitting unset optional fields; always include clear_description if True."""
        data = self.model_dump(exclude_none=True)
        if not self.clear_description:
            data.pop("clear_description", None)
        return data


class QrInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chore_id: int
    title: str
    qr_token: str
    qr_url: str
    png_path: str


class ChoreDeleteResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    deleted: bool
    chore_id: int
    completions_removed: int


class TimingBonuses(BaseModel):
    model_config = ConfigDict(extra="ignore")

    early_bonus_points: int
    on_time_bonus_points: int
    late_bonus_points: int


class AchievementAdmin(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    title: str
    description: str
    icon_key: str
    criteria_type: str
    threshold: int
    points_reward: int
    is_active: bool


class AchievementCreate(BaseModel):
    title: str
    description: str = ""
    icon_key: str = "star"
    criteria_type: str
    threshold: int = 1
    points_reward: int = 0


class AchievementUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    icon_key: str | None = None
    criteria_type: str | None = None
    threshold: int | None = None
    points_reward: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class RewardsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bonuses: TimingBonuses
    achievements: list[AchievementAdmin]
