"""Unit tests for /api/v1 router helper functions."""

import json

import pytest
from fastapi import HTTPException

from qr_chores.models.rewards import Achievement, CriteriaType
from qr_chores.routers.api.child import _completion_http_error
from qr_chores.routers.api.rewards import (
    _achievement_out,
    _criteria_json,
    _threshold_from_achievement,
)
from qr_chores.services.completion import CompletionError


def test_completion_http_error_shape() -> None:
    exc = CompletionError("Photo is required.", "photo_required")
    http = _completion_http_error(exc)
    assert isinstance(http, HTTPException)
    assert http.status_code == 400
    assert http.detail == {"message": "Photo is required.", "code": "photo_required"}


def test_criteria_json_streak_uses_days() -> None:
    payload = json.loads(_criteria_json(CriteriaType.streak_days, 7))
    assert payload == {"days": 7}


def test_criteria_json_count_types() -> None:
    for ct in (
        CriteriaType.total_completions,
        CriteriaType.complete_on_time_count,
        CriteriaType.complete_early_count,
        CriteriaType.photo_completions,
    ):
        payload = json.loads(_criteria_json(ct, 5))
        assert payload == {"count": 5}


def test_threshold_from_achievement_count() -> None:
    ach = Achievement(
        title="T",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.total_completions,
        criteria_json='{"count": 12}',
        points_reward=1,
        is_active=True,
    )
    assert _threshold_from_achievement(ach) == 12


def test_threshold_from_achievement_days() -> None:
    ach = Achievement(
        title="T",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.streak_days,
        criteria_json='{"days": 4}',
        points_reward=1,
        is_active=True,
    )
    assert _threshold_from_achievement(ach) == 4


def test_threshold_from_achievement_empty_and_invalid() -> None:
    empty = Achievement(
        title="T",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.total_completions,
        criteria_json="{}",
        points_reward=1,
        is_active=True,
    )
    assert _threshold_from_achievement(empty) == 1

    bad = Achievement(
        title="T",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.total_completions,
        criteria_json="not-json",
        points_reward=1,
        is_active=True,
    )
    assert _threshold_from_achievement(bad) == 1

    none_json = Achievement(
        title="T",
        description="",
        icon_key="star",
        criteria_type=CriteriaType.total_completions,
        criteria_json=None,  # type: ignore[arg-type]
        points_reward=1,
        is_active=True,
    )
    # criteria_json is str in model; exercise empty-ish path via ""
    none_json.criteria_json = ""
    assert _threshold_from_achievement(none_json) == 1


def test_achievement_out_maps_fields() -> None:
    ach = Achievement(
        id=42,
        title="Photo pro",
        description="Snap it",
        icon_key="camera",
        criteria_type=CriteriaType.photo_completions,
        criteria_json='{"count": 3}',
        points_reward=15,
        is_active=False,
    )
    out = _achievement_out(ach)
    assert out.id == 42
    assert out.title == "Photo pro"
    assert out.description == "Snap it"
    assert out.icon_key == "camera"
    assert out.criteria_type == "photo_completions"
    assert out.threshold == 3
    assert out.points_reward == 15
    assert out.is_active is False


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("not_scheduled", "Not scheduled today."),
        ("photo_too_large", "Too big."),
        ("already_done", "Already done."),
    ],
)
def test_completion_http_error_preserves_codes(code: str, message: str) -> None:
    http = _completion_http_error(CompletionError(message, code))
    assert http.detail["code"] == code  # type: ignore[index]
    assert http.detail["message"] == message  # type: ignore[index]
