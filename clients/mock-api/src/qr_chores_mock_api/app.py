"""FastAPI mock of /api/v1 for client library tests."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from qr_chores_mock_api.fixtures import (
    CHILD_EMAIL,
    CHILD_PASSWORD,
    CHILD_TOKEN,
    PARENT_EMAIL,
    PARENT_PASSWORD,
    PARENT_TOKEN,
    TINY_PNG,
    chore_out,
    completion_summary,
    fresh_state,
    now_iso,
    user_out,
)

app = FastAPI(title="QR Chores Mock API", version="0.1.0")
STATE: dict[str, Any] = fresh_state()


def reset_state() -> None:
    """Reset fixtures (used by tests)."""
    global STATE
    STATE = fresh_state()


class LoginRequest(BaseModel):
    email: str
    password: str


class ChoreCreate(BaseModel):
    title: str
    description: str | None = None
    due_time: str = "20:00:00"
    schedule_days: str = "0123456"
    photo_policy: str = "none"
    base_points: int = 10
    early_bonus_enabled: bool = True


class ChoreUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_time: str | None = None
    schedule_days: str | None = None
    photo_policy: str | None = None
    base_points: int | None = None
    early_bonus_enabled: bool | None = None
    clear_description: bool = False


class TimingBonusesUpdate(BaseModel):
    early_bonus_points: int = Field(ge=0)
    on_time_bonus_points: int = Field(ge=0)
    # Late may be negative (penalty).
    late_bonus_points: int = Field(ge=-1_000_000, le=1_000_000)


class AchievementWrite(BaseModel):
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


def _user_from_auth(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    email = STATE["tokens"].get(token)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return STATE["users"][email]


def require_auth(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return _user_from_auth(authorization)


def require_parent(user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    if user["role"] != "parent":
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user


def require_child(user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    if user["role"] != "child":
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user


def _chore_by_id(chore_id: int) -> dict[str, Any]:
    chore = STATE["chores"].get(chore_id)
    if not chore:
        raise HTTPException(status_code=404, detail="Chore not found")
    return chore


def _chore_by_token(qr_token: str) -> dict[str, Any]:
    for chore in STATE["chores"].values():
        if chore["qr_token"] == qr_token:
            return chore
    raise HTTPException(status_code=404, detail="Chore not found")


def _completion_for_chore_today(chore_id: int) -> dict[str, Any] | None:
    local_date = STATE["local_date"]
    for c in STATE["completions"].values():
        if c["chore_id"] == chore_id and c["local_date"] == local_date:
            return c
    return None


def _board_item(chore: dict[str, Any]) -> dict[str, Any]:
    completion = _completion_for_chore_today(chore["id"])
    done = completion is not None
    if done:
        status_label = "Done"
        status_kind = "done"
        is_late_pending = False
        timing = completion["timing"]
    else:
        status_label = "Pending"
        status_kind = "pending"
        is_late_pending = False
        timing = None
    return {
        "chore": chore_out(chore),
        "done": done,
        "status_label": status_label,
        "status_kind": status_kind,
        "is_late_pending": is_late_pending,
        "timing": timing,
        "completion": completion_summary(completion) if completion else None,
    }


@app.get("/healthz")
@app.get("/healthz/")
@app.get("/health")
@app.get("/health/")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/auth/login")
def login(body: LoginRequest) -> dict[str, Any]:
    user = STATE["users"].get(body.email)
    if not user or user["password"] != body.password:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    # Stable tokens for fixture accounts; random for any other.
    if body.email == PARENT_EMAIL and body.password == PARENT_PASSWORD:
        token = PARENT_TOKEN
    elif body.email == CHILD_EMAIL and body.password == CHILD_PASSWORD:
        token = CHILD_TOKEN
    else:
        token = secrets.token_urlsafe(16)
        STATE["tokens"][token] = body.email
    STATE["tokens"][token] = body.email
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 1_209_600,
        "user": user_out(user),
    }


@app.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(authorization: str | None = Header(default=None)) -> None:
    # Client discards bearer; no-op if missing.
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        # Keep fixture tokens mapped so re-login with same stable token still works;
        # only drop non-fixture tokens.
        if token not in (PARENT_TOKEN, CHILD_TOKEN):
            STATE["tokens"].pop(token, None)


@app.get("/api/v1/me")
def me(user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    return user_out(user)


@app.get("/api/v1/home")
def home(user: dict[str, Any] = Depends(require_child)) -> dict[str, Any]:
    active = [c for c in STATE["chores"].values() if c["is_active"]]
    board = [_board_item(c) for c in sorted(active, key=lambda x: x["id"])]
    done_count = sum(1 for b in board if b["done"])
    unlocks = []
    for ua in STATE["user_achievements"]:
        if ua["user_id"] == user["id"]:
            ach = STATE["achievements"][ua["achievement_id"]]
            unlocks.append(
                {
                    "id": ach["id"],
                    "title": ach["title"],
                    "description": ach["description"],
                    "icon_key": ach["icon_key"],
                    "points_reward": ach["points_reward"],
                    "unlocked_at": ua["unlocked_at"],
                }
            )
    return {
        "local_date": STATE["local_date"],
        "points_balance": user["points_balance"],
        "points_today": sum(
            c["points_awarded"]
            for c in STATE["completions"].values()
            if c["user_id"] == user["id"] and c["local_date"] == STATE["local_date"]
        ),
        "done_count": done_count,
        "total_count": len(board),
        "board": board,
        "recent_unlocks": unlocks,
    }


@app.get("/api/v1/c/{qr_token}")
def confirm(qr_token: str, user: dict[str, Any] = Depends(require_child)) -> dict[str, Any]:
    del user  # auth only
    chore = _chore_by_token(qr_token)
    if not chore["is_active"]:
        raise HTTPException(status_code=404, detail="Chore not found")
    completion = _completion_for_chore_today(chore["id"])
    return {
        "chore": chore_out(chore),
        "scheduled_today": True,
        "already_done": completion is not None,
        "is_late_pending": False,
        "completion": completion_summary(completion) if completion else None,
    }


@app.post("/api/v1/c/{qr_token}/complete")
async def complete(
    qr_token: str,
    photo: UploadFile | None = File(default=None),
    notes: str | None = Form(default=None),
    user: dict[str, Any] = Depends(require_child),
) -> dict[str, Any]:
    chore = _chore_by_token(qr_token)
    if not chore["is_active"]:
        raise HTTPException(status_code=404, detail="Chore not found")
    existing = _completion_for_chore_today(chore["id"])
    if existing:
        return {
            "already_done": True,
            "chore": chore_out(chore),
            "completion": completion_summary(existing),
            "points": {
                "base": 0,
                "timing_bonus": 0,
                "achievement_points": 0,
                "total": 0,
            },
            "unlocks": [],
        }

    photo_bytes: bytes | None = None
    if photo is not None:
        photo_bytes = await photo.read()
    if chore["photo_policy"] == "required" and not photo_bytes:
        raise HTTPException(
            status_code=400,
            detail={"message": "A photo is required for this chore.", "code": "photo_required"},
        )

    cid = STATE["next_completion_id"]
    STATE["next_completion_id"] = cid + 1
    timing = "on_time"
    bonus = STATE["bonuses"]["on_time_bonus_points"]
    total = chore["base_points"] + bonus
    clean_notes = notes.strip() if notes and notes.strip() else None
    completion = {
        "id": cid,
        "chore_id": chore["id"],
        "user_id": user["id"],
        "local_date": STATE["local_date"],
        "completed_at": now_iso(),
        "timing": timing,
        "points_awarded": total,
        "has_photo": bool(photo_bytes),
        "notes": clean_notes,
        "photo_bytes": photo_bytes or None,
    }
    STATE["completions"][cid] = completion
    user["points_balance"] += total

    return {
        "already_done": False,
        "chore": chore_out(chore),
        "completion": completion_summary(completion),
        "points": {
            "base": chore["base_points"],
            "timing_bonus": bonus,
            "achievement_points": 0,
            "total": total,
        },
        "unlocks": [],
    }


@app.get("/api/v1/achievements")
def achievements(user: dict[str, Any] = Depends(require_child)) -> dict[str, Any]:
    unlocked_ids = {
        ua["achievement_id"] for ua in STATE["user_achievements"] if ua["user_id"] == user["id"]
    }
    items = []
    for ach in STATE["achievements"].values():
        unlocked = ach["id"] in unlocked_ids
        progress = ach["threshold"] if unlocked else 0
        items.append(
            {
                "id": ach["id"],
                "title": ach["title"],
                "description": ach["description"],
                "icon_key": ach["icon_key"],
                "criteria_type": ach["criteria_type"],
                "points_reward": ach["points_reward"],
                "unlocked": unlocked,
                "progress": progress,
                "threshold": ach["threshold"],
                "percent": 100 if unlocked else 0,
            }
        )
    return {
        "points_balance": user["points_balance"],
        "unlocked_count": len(unlocked_ids),
        "achievements": items,
    }


@app.get("/api/v1/today")
def today(user: dict[str, Any] = Depends(require_parent)) -> dict[str, Any]:
    del user
    active = [c for c in STATE["chores"].values() if c["is_active"]]
    board = [_board_item(c) for c in active]

    def sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
        done = item["done"]
        is_late_pending = item["is_late_pending"]
        timing = item["timing"]
        if not done:
            rank = 0 if is_late_pending else 1
        else:
            if timing == "late":
                rank = 2
            elif timing == "early":
                rank = 3
            else:
                rank = 4
        return (rank, item["chore"]["due_time"], item["chore"]["title"])

    board.sort(key=sort_key)
    return {"local_date": STATE["local_date"], "board": board}


@app.get("/api/v1/history")
def history(
    child_id: int | None = Query(default=None),
    chore_id: int | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    timing: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    user: dict[str, Any] = Depends(require_parent),
) -> dict[str, Any]:
    del user
    all_completions = list(STATE["completions"].values())

    filtered = []
    for c in all_completions:
        if child_id is not None and c["user_id"] != child_id:
            continue
        if chore_id is not None and c["chore_id"] != chore_id:
            continue
        if start_date and c["local_date"] < start_date:
            continue
        if end_date and c["local_date"] > end_date:
            continue
        if timing and c["timing"] != timing:
            continue
        filtered.append(c)

    filtered.sort(key=lambda x: x["id"], reverse=True)
    total_count = len(filtered)
    import math

    total_pages = math.ceil(total_count / limit) if total_count > 0 else 1
    page = max(1, min(page, total_pages))
    offset = (page - 1) * limit
    paginated = filtered[offset : offset + limit]

    items = []
    for c in paginated:
        chore = STATE["chores"].get(c["chore_id"], {"title": "?", "id": c["chore_id"]})
        items.append(
            {
                "completion": completion_summary(c),
                "chore_id": c["chore_id"],
                "chore_title": chore.get("title", "?"),
                "user_id": c["user_id"],
            }
        )

    on_time_count = sum(1 for c in filtered if c["timing"] in ("on_time", "early"))
    on_time_rate = round((on_time_count / total_count) * 100, 1) if total_count > 0 else 0.0
    total_points = sum(c["points_awarded"] for c in filtered)

    stats = {
        "total_completions": total_count,
        "completions_this_week": total_count,
        "on_time_count": on_time_count,
        "on_time_rate": on_time_rate,
        "total_points": total_points,
        "current_streak": 1 if total_count > 0 else 0,
    }

    pagination = {
        "page": page,
        "limit": limit,
        "total_count": total_count,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }

    return {
        "items": items,
        "limit": limit,
        "stats": stats,
        "pagination": pagination,
    }


@app.post("/api/v1/completions/{completion_id}/undo")
def undo_completion_mock(
    completion_id: int,
    user: dict[str, Any] = Depends(require_parent),
) -> dict[str, Any]:
    del user
    comp = STATE["completions"].get(completion_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Completion not found")

    chore_id = comp["chore_id"]
    points_reverted = comp.get("points_awarded", 0)

    del STATE["completions"][completion_id]

    return {
        "success": True,
        "completion_id": completion_id,
        "chore_id": chore_id,
        "points_reverted": points_reverted,
    }



@app.get("/api/v1/chores")
def list_chores(
    include_inactive: bool = Query(default=True),
    user: dict[str, Any] = Depends(require_parent),
) -> dict[str, Any]:
    del user
    chores = list(STATE["chores"].values())
    if not include_inactive:
        chores = [c for c in chores if c["is_active"]]
    chores = sorted(chores, key=lambda x: x["id"])
    return {"chores": [chore_out(c) for c in chores]}


@app.post("/api/v1/chores", status_code=status.HTTP_201_CREATED)
def create_chore(body: ChoreCreate, user: dict[str, Any] = Depends(require_parent)) -> dict[str, Any]:
    del user
    cid = STATE["next_chore_id"]
    STATE["next_chore_id"] = cid + 1
    chore = {
        "id": cid,
        "title": body.title.strip(),
        "description": body.description,
        "qr_token": f"qr-gen-{cid}",
        "due_time": body.due_time,
        "schedule_days": body.schedule_days or "0123456",
        "photo_policy": body.photo_policy,
        "base_points": body.base_points,
        "early_bonus_enabled": body.early_bonus_enabled,
        "is_active": True,
    }
    STATE["chores"][cid] = chore
    return chore_out(chore)


@app.get("/api/v1/chores/{chore_id}")
def get_chore(chore_id: int, user: dict[str, Any] = Depends(require_parent)) -> dict[str, Any]:
    del user
    return chore_out(_chore_by_id(chore_id))


@app.patch("/api/v1/chores/{chore_id}")
def update_chore(
    chore_id: int,
    body: ChoreUpdate,
    user: dict[str, Any] = Depends(require_parent),
) -> dict[str, Any]:
    del user
    chore = _chore_by_id(chore_id)
    data = body.model_dump(exclude_unset=True)
    clear = data.pop("clear_description", False)
    for key, value in data.items():
        if value is not None:
            chore[key] = value
    if clear:
        chore["description"] = None
    return chore_out(chore)


@app.post("/api/v1/chores/{chore_id}/deactivate")
def deactivate_chore(
    chore_id: int, user: dict[str, Any] = Depends(require_parent)
) -> dict[str, Any]:
    del user
    chore = _chore_by_id(chore_id)
    chore["is_active"] = False
    return chore_out(chore)


@app.post("/api/v1/chores/{chore_id}/activate")
def activate_chore(chore_id: int, user: dict[str, Any] = Depends(require_parent)) -> dict[str, Any]:
    del user
    chore = _chore_by_id(chore_id)
    chore["is_active"] = True
    return chore_out(chore)


@app.delete("/api/v1/chores/{chore_id}")
def delete_chore(chore_id: int, user: dict[str, Any] = Depends(require_parent)) -> dict[str, Any]:
    del user
    if chore_id not in STATE["chores"]:
        raise HTTPException(status_code=404, detail="Chore not found")
    del STATE["chores"][chore_id]
    removed = [cid for cid, c in list(STATE["completions"].items()) if c["chore_id"] == chore_id]
    for cid in removed:
        del STATE["completions"][cid]
    return {
        "deleted": True,
        "chore_id": chore_id,
        "completions_removed": len(removed),
    }


@app.get("/api/v1/chores/{chore_id}/qr")
def qr_info(chore_id: int, user: dict[str, Any] = Depends(require_parent)) -> dict[str, Any]:
    del user
    chore = _chore_by_id(chore_id)
    return {
        "chore_id": chore["id"],
        "title": chore["title"],
        "qr_token": chore["qr_token"],
        "qr_url": f"http://testserver/c/{chore['qr_token']}",
        "png_path": f"/api/v1/chores/{chore_id}/qr.png",
    }


@app.get("/api/v1/chores/{chore_id}/qr.png")
def qr_png(chore_id: int, user: dict[str, Any] = Depends(require_parent)) -> Response:
    del user
    _chore_by_id(chore_id)
    return Response(content=TINY_PNG, media_type="image/png")


@app.get("/api/v1/rewards")
def rewards(user: dict[str, Any] = Depends(require_parent)) -> dict[str, Any]:
    del user
    achievements = [
        {
            "id": a["id"],
            "title": a["title"],
            "description": a["description"],
            "icon_key": a["icon_key"],
            "criteria_type": a["criteria_type"],
            "threshold": a["threshold"],
            "points_reward": a["points_reward"],
            "is_active": a["is_active"],
        }
        for a in sorted(STATE["achievements"].values(), key=lambda x: x["id"])
    ]
    return {"bonuses": dict(STATE["bonuses"]), "achievements": achievements}


@app.put("/api/v1/rewards/bonuses")
def update_bonuses(
    body: TimingBonusesUpdate, user: dict[str, Any] = Depends(require_parent)
) -> dict[str, Any]:
    del user
    STATE["bonuses"] = body.model_dump()
    return dict(STATE["bonuses"])


@app.post("/api/v1/rewards/achievements", status_code=status.HTTP_201_CREATED)
def create_achievement(
    body: AchievementWrite, user: dict[str, Any] = Depends(require_parent)
) -> dict[str, Any]:
    del user
    aid = STATE["next_achievement_id"]
    STATE["next_achievement_id"] = aid + 1
    ach = {
        "id": aid,
        "title": body.title.strip(),
        "description": body.description,
        "icon_key": body.icon_key or "star",
        "criteria_type": body.criteria_type,
        "threshold": body.threshold,
        "points_reward": body.points_reward,
        "is_active": True,
    }
    STATE["achievements"][aid] = ach
    return {
        "id": ach["id"],
        "title": ach["title"],
        "description": ach["description"],
        "icon_key": ach["icon_key"],
        "criteria_type": ach["criteria_type"],
        "threshold": ach["threshold"],
        "points_reward": ach["points_reward"],
        "is_active": ach["is_active"],
    }


@app.patch("/api/v1/rewards/achievements/{achievement_id}")
def update_achievement(
    achievement_id: int,
    body: AchievementUpdate,
    user: dict[str, Any] = Depends(require_parent),
) -> dict[str, Any]:
    del user
    ach = STATE["achievements"].get(achievement_id)
    if not ach:
        raise HTTPException(status_code=404, detail="Achievement not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            ach[key] = value
    return {
        "id": ach["id"],
        "title": ach["title"],
        "description": ach["description"],
        "icon_key": ach["icon_key"],
        "criteria_type": ach["criteria_type"],
        "threshold": ach["threshold"],
        "points_reward": ach["points_reward"],
        "is_active": ach["is_active"],
    }


@app.post("/api/v1/rewards/achievements/{achievement_id}/toggle")
def toggle_achievement(
    achievement_id: int, user: dict[str, Any] = Depends(require_parent)
) -> dict[str, Any]:
    del user
    ach = STATE["achievements"].get(achievement_id)
    if not ach:
        raise HTTPException(status_code=404, detail="Achievement not found")
    ach["is_active"] = not ach["is_active"]
    return {
        "id": ach["id"],
        "title": ach["title"],
        "description": ach["description"],
        "icon_key": ach["icon_key"],
        "criteria_type": ach["criteria_type"],
        "threshold": ach["threshold"],
        "points_reward": ach["points_reward"],
        "is_active": ach["is_active"],
    }


@app.get("/api/v1/photos/{completion_id}")
def get_photo(
    completion_id: int, user: dict[str, Any] = Depends(require_auth)
) -> Response:
    del user
    completion = STATE["completions"].get(completion_id)
    if not completion or not completion.get("has_photo"):
        raise HTTPException(status_code=404, detail="Photo not found")
    data = completion.get("photo_bytes") or TINY_PNG
    return Response(content=data, media_type="image/png")
