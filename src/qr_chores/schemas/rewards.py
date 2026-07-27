"""Rewards admin schemas for /api/v1."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TimingBonusesOut(BaseModel):
    early_bonus_points: int
    on_time_bonus_points: int
    late_bonus_points: int


class TimingBonusesUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "early_bonus_points": 5,
                    "on_time_bonus_points": 2,
                    "late_bonus_points": 0,
                }
            ]
        }
    )

    early_bonus_points: Annotated[int, Field(ge=0, le=1_000_000)]
    on_time_bonus_points: Annotated[int, Field(ge=0, le=1_000_000)]
    # Late may be negative so parents can set a late penalty (e.g. -2).
    late_bonus_points: Annotated[int, Field(ge=-1_000_000, le=1_000_000)]


class AchievementAdminOut(BaseModel):
    id: int
    title: str
    description: str
    icon_key: str
    criteria_type: str
    threshold: int
    points_reward: int
    is_active: bool


class AchievementWrite(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "title": "Early bird",
                    "description": "Complete early 5 times",
                    "icon_key": "bird",
                    "criteria_type": "complete_early_count",
                    "threshold": 5,
                    "points_reward": 25,
                }
            ]
        }
    )

    title: Annotated[str, Field(min_length=1, max_length=120)]
    description: str = ""
    icon_key: str = "star"
    criteria_type: str
    threshold: Annotated[int, Field(ge=1, le=1_000_000)] = 1
    points_reward: Annotated[int, Field(ge=0, le=1_000_000)] = 0

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Title is required.")
        return stripped

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("icon_key")
    @classmethod
    def strip_icon(cls, value: str) -> str:
        return (value or "star").strip() or "star"

    @field_validator("criteria_type")
    @classmethod
    def validate_criteria_type(cls, value: str) -> str:
        allowed = {
            "total_completions",
            "complete_on_time_count",
            "complete_early_count",
            "photo_completions",
            "streak_days",
        }
        if value not in allowed:
            raise ValueError(f"criteria_type must be one of {sorted(allowed)}")
        return value


class AchievementCreate(AchievementWrite):
    pass


class AchievementUpdate(BaseModel):
    title: Annotated[str | None, Field(default=None, min_length=1, max_length=120)] = None
    description: str | None = None
    icon_key: str | None = None
    criteria_type: str | None = None
    threshold: Annotated[int | None, Field(default=None, ge=1, le=1_000_000)] = None
    points_reward: Annotated[int | None, Field(default=None, ge=0, le=1_000_000)] = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Title is required.")
        return stripped

    @field_validator("criteria_type")
    @classmethod
    def validate_criteria_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {
            "total_completions",
            "complete_on_time_count",
            "complete_early_count",
            "photo_completions",
            "streak_days",
        }
        if value not in allowed:
            raise ValueError(f"criteria_type must be one of {sorted(allowed)}")
        return value


class RewardsResponse(BaseModel):
    bonuses: TimingBonusesOut
    achievements: list[AchievementAdminOut]
