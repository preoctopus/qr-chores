# Client contract — `/api/v1`

Shared source of truth for `clients/mock-api`, `clients/python`, and `clients/kotlin`.
Wire format matches the real server (`docs/API.md`).

Base path: **`/api/v1`**

## Fixture accounts (mock-api)

| Role | Email | Password |
|------|-------|----------|
| parent | `parent@example.com` | `parent-pass` |
| child | `child@example.com` | `child-pass` |

Login issues opaque bearer tokens: `parent-token` / `child-token` (stable for tests).

## Seed data

- **Parent user id 1** / **Child user id 2** (seed accounts above). Child has `parent_id=1`.
- **Chore 1** (active): title `Unload dishwasher`, `qr_token=qr-active-1`, due `20:00:00`, schedule `0123456`, photo_policy `optional`, base_points `10`
- **Chore 2** (active): title `Make bed`, `qr_token=qr-photo-required`, due `09:00:00`, schedule `0123456`, photo_policy `required`, base_points `5`
- **Chore 3** (inactive): title `Old chore`, `qr_token=qr-inactive`, photo_policy `none`, base_points `1`
- **Completion 1**: chore 1, local_date today, timing `on_time`, points `12`, has photo
- **Achievement 1**: Early bird, `complete_early_count`, threshold 5, points_reward 25, active
- **Bonuses**: early 5, on_time 2, late 0

Tiny valid PNG bytes served for `GET .../qr.png` and `GET .../photos/{id}`.

## Endpoint → client methods

| HTTP | Path | Python | Kotlin |
|------|------|--------|--------|
| POST | `/api/v1/auth/login` | `login` | `login` |
| POST | `/api/v1/auth/logout` | `logout` | `logout` |
| GET | `/api/v1/me` | `get_me` | `getMe` |
| GET | `/api/v1/home` | `get_home` | `getHome` |
| GET | `/api/v1/c/{qr_token}` | `get_confirm` | `getConfirm` |
| POST | `/api/v1/c/{qr_token}/complete` | `complete_chore` | `completeChore` |

- `POST /api/v1/c/{qr_token}/complete`: accepts optional multipart/form `photo` bytes and/or optional `notes` string for parents. `Completion` DTO includes `notes: string | null`.
| GET | `/api/v1/achievements` | `get_achievements` | `getAchievements` |
| GET | `/api/v1/today` | `get_today` | `getToday` |
| GET | `/api/v1/history` | `get_history` | `getHistory` |
| GET | `/api/v1/children` | `list_children` | `listChildren` |
| POST | `/api/v1/children` | `create_child` | `createChild` |
| GET | `/api/v1/children/{id}` | `get_child` | `getChild` |
| PATCH | `/api/v1/children/{id}` | `update_child` | `updateChild` |
| POST | `/api/v1/children/{id}/activate` | `activate_child` | `activateChild` |
| POST | `/api/v1/children/{id}/deactivate` | `deactivate_child` | `deactivateChild` |
| GET | `/api/v1/chores` | `list_chores` | `listChores` |
| POST | `/api/v1/chores` | `create_chore` | `createChore` |
| GET | `/api/v1/chores/{id}` | `get_chore` | `getChore` |
| PATCH | `/api/v1/chores/{id}` | `update_chore` | `updateChore` |
| DELETE | `/api/v1/chores/{id}` | `delete_chore` | `deleteChore` |
| POST | `/api/v1/chores/{id}/activate` | `activate_chore` | `activateChore` |
| POST | `/api/v1/chores/{id}/deactivate` | `deactivate_chore` | `deactivateChore` |
| GET | `/api/v1/chores/{id}/qr` | `get_qr_info` | `getQrInfo` |
| GET | `/api/v1/chores/{id}/qr.png` | `get_qr_png` | `getQrPng` |
| GET | `/api/v1/rewards` | `get_rewards` | `getRewards` |
| PUT | `/api/v1/rewards/bonuses` | `update_bonuses` | `updateBonuses` |
| POST | `/api/v1/rewards/achievements` | `create_achievement` | `createAchievement` |
| PATCH | `/api/v1/rewards/achievements/{id}` | `update_achievement` | `updateAchievement` |
| POST | `/api/v1/rewards/achievements/{id}/toggle` | `toggle_achievement` | `toggleAchievement` |
| GET | `/api/v1/photos/{completion_id}` | `get_photo` | `getPhoto` |

## Errors

| Status | Exception (Python / Kotlin) | Body |
|--------|----------------------------|------|
| 401 | `AuthError` / `AuthException` | `{ "detail": "…" }` string |
| 403 | `ForbiddenError` / `ForbiddenException` | string detail |
| 404 | `NotFoundError` / `NotFoundException` | string detail |
| 400 | `DomainError` / `DomainException` | Prefer `{ "detail": { "message", "code" } }`. Plain string detail → same exception with `code="domain_error"`. |
| 422 | `ValidationError` / `ValidationException` | FastAPI-style list under detail |

**Logout:** best-effort — always clear the local token; do not fail the caller if the server returns 401 (or other errors are swallowed after clear).

## JSON field names

Wire format uses **snake_case** in both clients (Kotlin `@SerialName` / default kotlinx.serialization with snake_case policy).

## Running mock-api

```bash
cd clients/mock-api
uv sync
uv run uvicorn qr_chores_mock_api.app:app --host 127.0.0.1 --port 18080
```

`GET /health` or `GET /healthz` → `{"status":"ok"}`.
