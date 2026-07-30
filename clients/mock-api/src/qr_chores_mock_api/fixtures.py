"""Seed data and tiny PNG for the mock API."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, time
from typing import Any

# 1x1 transparent PNG
TINY_PNG: bytes = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

PARENT_EMAIL = "parent@example.com"
PARENT_PASSWORD = "parent-pass"
CHILD_EMAIL = "child@example.com"
CHILD_PASSWORD = "child-pass"

PARENT_TOKEN = "parent-token"
CHILD_TOKEN = "child-token"


def today_iso() -> str:
    return datetime.now(UTC).date().isoformat()


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def initial_state() -> dict[str, Any]:
    local_date = today_iso()
    completed_at = now_iso()
    return {
        "users": {
            PARENT_EMAIL: {
                "id": 1,
                "email": PARENT_EMAIL,
                "first_name": "Parent",
                "last_name": "User",
                "display_name": "Parent User",
                "role": "parent",
                "password": PARENT_PASSWORD,
                "points_balance": 0,
                "parent_id": None,
                "is_active": True,
            },
            CHILD_EMAIL: {
                "id": 2,
                "email": CHILD_EMAIL,
                "first_name": "Child",
                "last_name": "User",
                "display_name": "Child User",
                "role": "child",
                "password": CHILD_PASSWORD,
                "points_balance": 42,
                "parent_id": 1,
                "is_active": True,
            },
        },
        "tokens": {
            PARENT_TOKEN: PARENT_EMAIL,
            CHILD_TOKEN: CHILD_EMAIL,
        },
        "next_user_id": 3,
        "next_chore_id": 4,
        "next_achievement_id": 2,
        "next_completion_id": 2,
        "bonuses": {
            "early_bonus_points": 5,
            "on_time_bonus_points": 2,
            "late_bonus_points": 0,
        },
        "chores": {
            1: {
                "id": 1,
                "title": "Unload dishwasher",
                "description": "Empty top rack first",
                "qr_token": "qr-active-1",
                "due_time": "20:00:00",
                "schedule_days": "0123456",
                "photo_policy": "optional",
                "base_points": 10,
                "early_bonus_enabled": True,
                "is_active": True,
            },
            2: {
                "id": 2,
                "title": "Make bed",
                "description": None,
                "qr_token": "qr-photo-required",
                "due_time": "09:00:00",
                "schedule_days": "0123456",
                "photo_policy": "required",
                "base_points": 5,
                "early_bonus_enabled": True,
                "is_active": True,
            },
            3: {
                "id": 3,
                "title": "Old chore",
                "description": "Retired",
                "qr_token": "qr-inactive",
                "due_time": "12:00:00",
                "schedule_days": "0123456",
                "photo_policy": "none",
                "base_points": 1,
                "early_bonus_enabled": True,
                "is_active": False,
            },
        },
        "completions": {
            1: {
                "id": 1,
                "chore_id": 1,
                "user_id": 2,
                "local_date": local_date,
                "completed_at": completed_at,
                "timing": "on_time",
                "points_awarded": 12,
                "has_photo": True,
                "photo_bytes": TINY_PNG,
            },
        },
        "achievements": {
            1: {
                "id": 1,
                "title": "Early bird",
                "description": "Complete 5 early chores",
                "icon_key": "star",
                "criteria_type": "complete_early_count",
                "threshold": 5,
                "points_reward": 25,
                "is_active": True,
            },
        },
        "user_achievements": [
            {
                "user_id": 2,
                "achievement_id": 1,
                "unlocked_at": completed_at,
            }
        ],
        "local_date": local_date,
    }


def fresh_state() -> dict[str, Any]:
    return deepcopy(initial_state())


def completion_summary(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": c["id"],
        "local_date": c["local_date"],
        "completed_at": c["completed_at"],
        "timing": c["timing"],
        "points_awarded": c["points_awarded"],
        "has_photo": c["has_photo"],
        "notes": c.get("notes"),
    }


def user_out(u: dict[str, Any]) -> dict[str, Any]:
    first = u.get("first_name") or ""
    last = u.get("last_name") or ""
    display = u.get("display_name") or f"{first} {last}".strip() or u["email"]
    return {
        "id": u["id"],
        "email": u["email"],
        "first_name": first,
        "last_name": last,
        "display_name": display,
        "role": u["role"],
        "parent_id": u.get("parent_id"),
        "is_active": u.get("is_active", True),
        "points_balance": u["points_balance"],
    }


def chore_out(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": c["id"],
        "title": c["title"],
        "description": c["description"],
        "qr_token": c["qr_token"],
        "due_time": c["due_time"] if isinstance(c["due_time"], str) else time.isoformat(c["due_time"]),
        "schedule_days": c["schedule_days"],
        "photo_policy": c["photo_policy"],
        "base_points": c["base_points"],
        "early_bonus_enabled": c.get("early_bonus_enabled", True),
        "is_active": c["is_active"],
    }
