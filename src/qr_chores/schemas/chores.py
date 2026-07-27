"""Chore and board schemas for /api/v1."""

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field


class ChoreSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    qr_token: str
    due_time: time
    schedule_days: str
    photo_policy: str
    base_points: int
    is_active: bool
    assignee_user_id: int | None = None
    assignee_name: str | None = None


class CompletionSummaryOut(BaseModel):
    id: int
    local_date: date
    completed_at: datetime
    timing: str
    points_awarded: int
    has_photo: bool


class BoardItemOut(BaseModel):
    chore: ChoreSummaryOut
    done: bool
    status_label: str
    status_kind: str
    is_late_pending: bool
    timing: str | None = None
    completion: CompletionSummaryOut | None = None


class UnlockOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    icon_key: str
    points_reward: int
    unlocked_at: datetime | None = None


class HomeResponse(BaseModel):
    local_date: date
    points_balance: int
    points_today: int
    done_count: int
    total_count: int
    board: list[BoardItemOut]
    recent_unlocks: list[UnlockOut] = Field(default_factory=list)


class ChoreConfirmOut(BaseModel):
    chore: ChoreSummaryOut
    scheduled_today: bool
    already_done: bool
    is_late_pending: bool
    completion: CompletionSummaryOut | None = None


class AchievementProgressOut(BaseModel):
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
    points_balance: int
    unlocked_count: int
    achievements: list[AchievementProgressOut]


class PointsBreakdownOut(BaseModel):
    base: int
    timing_bonus: int
    achievement_points: int
    total: int


class CompleteResponse(BaseModel):
    already_done: bool
    chore: ChoreSummaryOut
    completion: CompletionSummaryOut
    points: PointsBreakdownOut
    unlocks: list[UnlockOut] = Field(default_factory=list)
