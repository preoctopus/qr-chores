"""Parent board, history, and chore write schemas for /api/v1."""

from datetime import date, time
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from qr_chores.schemas.chores import BoardItemOut, ChoreSummaryOut, CompletionSummaryOut


class TodayResponse(BaseModel):
    local_date: date
    board: list[BoardItemOut]


class HistoryItemOut(BaseModel):
    completion: CompletionSummaryOut
    chore_id: int
    chore_title: str
    user_id: int


class HistoryStatsOut(BaseModel):
    total_completions: int
    completions_this_week: int
    on_time_count: int
    on_time_rate: float
    total_points: int
    current_streak: int


class HistoryPaginationOut(BaseModel):
    page: int
    limit: int
    total_count: int
    total_pages: int
    has_next: bool
    has_prev: bool


class HistoryResponse(BaseModel):
    items: list[HistoryItemOut]
    limit: int
    stats: HistoryStatsOut | None = None
    pagination: HistoryPaginationOut | None = None


class ChoreListResponse(BaseModel):
    chores: list[ChoreSummaryOut]


class ChoreWrite(BaseModel):
    """Shared create/update fields for chores."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "title": "Unload dishwasher",
                    "description": "Empty top rack first",
                    "due_time": "20:00:00",
                    "schedule_days": "0123456",
                    "photo_policy": "optional",
                    "base_points": 10,
                    "assignee_user_id": 3,
                }
            ]
        }
    )

    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: str | None = None
    due_time: time
    schedule_days: str = "0123456"
    photo_policy: str = "none"
    base_points: Annotated[int, Field(ge=0, le=1_000_000)] = 10
    early_bonus_enabled: bool = True
    assignee_user_id: int

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Title is required.")
        return stripped

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("schedule_days")
    @classmethod
    def validate_schedule_days(cls, value: str) -> str:
        digits = "".join(sorted({c for c in value if c in "0123456"}))
        return digits or "0123456"

    @field_validator("photo_policy")
    @classmethod
    def validate_photo_policy(cls, value: str) -> str:
        allowed = {"required", "optional", "none"}
        if value not in allowed:
            raise ValueError(f"photo_policy must be one of {sorted(allowed)}")
        return value


class ChoreCreate(ChoreWrite):
    pass


class ChoreUpdate(BaseModel):
    """Partial update; omitted fields are left unchanged."""

    title: Annotated[str | None, Field(default=None, min_length=1, max_length=200)] = None
    description: str | None = None
    due_time: time | None = None
    schedule_days: str | None = None
    photo_policy: str | None = None
    base_points: Annotated[int | None, Field(default=None, ge=0, le=1_000_000)] = None
    early_bonus_enabled: bool | None = None
    assignee_user_id: int | None = None
    clear_description: bool = False

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Title is required.")
        return stripped

    @field_validator("schedule_days")
    @classmethod
    def validate_schedule_days(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = "".join(sorted({c for c in value if c in "0123456"}))
        return digits or "0123456"

    @field_validator("photo_policy")
    @classmethod
    def validate_photo_policy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {"required", "optional", "none"}
        if value not in allowed:
            raise ValueError(f"photo_policy must be one of {sorted(allowed)}")
        return value


class QrInfoOut(BaseModel):
    chore_id: int
    title: str
    qr_token: str
    qr_url: str
    png_path: str


class ChoreDeleteResponse(BaseModel):
    deleted: bool
    chore_id: int
    completions_removed: int


class UndoCompletionResponse(BaseModel):
    success: bool = True
    completion_id: int
    chore_id: int
    points_reverted: int
