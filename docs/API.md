# Internal JSON API (`/api/v1`)

**Audience:** native iOS/Android clients, automation, MCP, and other non-browser integrations.  
**Not** end-user documentation — family members use the HTML app and `/help`.

This surface is **internal**: it is versioned and documented for first-party apps. It is not a public multi-tenant product API. Auth, roles, and product rules match the server-rendered app.

Base path: **`/api/v1`**

In non-production (`ENVIRONMENT=development`), interactive OpenAPI is available at `/docs` and `/openapi.json`. Production keeps those disabled.

---

## Authentication

### Overview

| Mechanism | How | Use case |
|-----------|-----|----------|
| **Bearer token** | `Authorization: Bearer <access_token>` | Native apps, scripts, MCP (preferred) |
| **Session cookie** | Same HTTP-only cookie as the HTML UI | Browser same-origin callers |

Protected routes require one of the above. Missing or invalid credentials → **`401 Unauthorized`** with JSON body:

```json
{ "detail": "Not authenticated" }
```

Wrong role (e.g. parent token on a child-only route) → **`403 Forbidden`**:

```json
{ "detail": "Insufficient permissions" }
```

### Login

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "daughter@example.com",
  "password": "child-pass"
}
```

**Success `200`:**

```json
{
  "access_token": "<opaque signed token>",
  "token_type": "bearer",
  "expires_in": 1209600,
  "user": {
    "id": 1,
    "email": "daughter@example.com",
    "display_name": "Daughter",
    "role": "child",
    "points_balance": 0
  }
}
```

**Failure `401`:** invalid email/password → `{ "detail": "Invalid email or password." }`

Also sets the normal session cookie (optional convenience). Native clients should store **`access_token`** securely (Keychain / EncryptedSharedPreferences) and send it on every request.

`expires_in` is seconds (same lifetime as the HTML session, default 14 days). Tokens are **opaque signed values** (not JWTs). They cannot be revoked server-side without rotating `SECRET_KEY` or waiting for expiry; discard on logout.

### Authenticated requests

```http
GET /api/v1/me
Authorization: Bearer <access_token>
Accept: application/json
```

### Logout

```http
POST /api/v1/auth/logout
```

Clears the session cookie. Bearer tokens are discarded by the client (not blacklisted).

### Current user

```http
GET /api/v1/me
```

Requires auth. Returns `UserOut` (`id`, `email`, `display_name`, `role`, `points_balance`).

---

## Child endpoints

All require **`role=child`** (and authentication).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/home` | Today’s board, points, recent unlocks |
| `GET` | `/api/v1/c/{qr_token}` | Confirm payload for a chore QR |
| `POST` | `/api/v1/c/{qr_token}/complete` | Complete chore (optional multipart photo) |
| `GET` | `/api/v1/achievements` | Achievement progress |

### Complete chore

```http
POST /api/v1/c/{qr_token}/complete
Authorization: Bearer <child_token>
Content-Type: multipart/form-data
```

Optional form field: **`photo`** (JPEG / PNG / WebP; size capped by `PHOTO_MAX_BYTES`).

**Success `200`:** includes `already_done`, `chore`, `completion`, `points` breakdown, `unlocks`.

Domain failures (not scheduled, photo required, too large, etc.) → **`400`** with:

```json
{
  "detail": {
    "message": "…",
    "code": "photo_required"
  }
}
```

Unknown / inactive QR → **`404`**.

Product rules are identical to the HTML flow: one completion per chore per local day, server-side points and achievements, child login required.

---

## Parent endpoints

All require **`role=parent`** (and authentication), except photo fetch (any authenticated user).

### Board & history

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/today` | Today’s status board (same domain rules as `/today`) |
| `GET` | `/api/v1/history?limit=50` | Recent completions (default 50, max 200) |

### Chores

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/chores` | List chores (`include_inactive`, default true) |
| `POST` | `/api/v1/chores` | Create chore (assigns stable `qr_token`) |
| `GET` | `/api/v1/chores/{id}` | Chore detail |
| `PATCH` | `/api/v1/chores/{id}` | Partial update |
| `POST` | `/api/v1/chores/{id}/deactivate` | Soft-stop QR (keep history) |
| `POST` | `/api/v1/chores/{id}/activate` | Re-activate |
| `DELETE` | `/api/v1/chores/{id}` | Hard delete + completions + photo files |
| `GET` | `/api/v1/chores/{id}/qr` | QR metadata (`qr_url`, `png_path`) |
| `GET` | `/api/v1/chores/{id}/qr.png` | QR PNG bytes |

**Create body example:**

```json
{
  "title": "Unload dishwasher",
  "description": "Empty top rack first",
  "due_time": "20:00:00",
  "schedule_days": "0123456",
  "photo_policy": "optional",
  "base_points": 10
}
```

`schedule_days` is a string of weekday digits (`0`=Mon … `6`=Sun). `photo_policy`: `required` | `optional` | `none`.

**PATCH** accepts any subset of create fields. Set `clear_description: true` to null out description.

### Rewards

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/rewards` | Timing bonuses + achievements |
| `PUT` | `/api/v1/rewards/bonuses` | Replace timing bonus points |
| `POST` | `/api/v1/rewards/achievements` | Create achievement |
| `PATCH` | `/api/v1/rewards/achievements/{id}` | Update achievement |
| `POST` | `/api/v1/rewards/achievements/{id}/toggle` | Toggle `is_active` |

**Bonuses body:**

```json
{
  "early_bonus_points": 5,
  "on_time_bonus_points": 2,
  "late_bonus_points": 0
}
```

**Achievement create body:**

```json
{
  "title": "Early bird",
  "description": "Complete early 5 times",
  "icon_key": "bird",
  "criteria_type": "complete_early_count",
  "threshold": 5,
  "points_reward": 25
}
```

`criteria_type`: `total_completions` | `complete_on_time_count` | `complete_early_count` | `photo_completions` | `streak_days`.

### Photos

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/photos/{completion_id}` | Any auth | Stream proof photo bytes |

Same access rules as HTML `GET /photos/{completion_id}`. Missing / no photo → **404**.

---

## Errors

All `/api/*` responses use **JSON** bodies (never HTML login redirects or error pages).

| Status | When | `detail` shape |
|--------|------|----------------|
| **401** | Missing/invalid auth or bad login | string, e.g. `"Not authenticated"` |
| **403** | Authenticated but wrong role | string, e.g. `"Insufficient permissions"` |
| **404** | Unknown chore / QR / photo / achievement | string message |
| **400** | Domain rule on complete (photo required, not scheduled, etc.) | object: `{ "message": "…", "code": "photo_required" }` |
| **422** | Pydantic/query validation | FastAPI list of field errors |

Common complete `code` values: `photo_required`, `photo_invalid`, `photo_too_large`, `not_scheduled`, and similar domain codes from `services/completion.py`.

Validation errors keep FastAPI’s default structure (array under `detail`). Auth/role/not-found use a plain string `detail` for simplicity.

**Deferred:** login rate limiting (nice-to-have; not implemented).

---

## OpenAPI

| Environment | Interactive docs |
|-------------|------------------|
| `development` (default) | `/docs`, `/redoc`, `/openapi.json` |
| `production` | Disabled |

OpenAPI includes a **BearerAuth** security scheme. Request bodies for login, chore create, bonuses, and achievements include examples.

---

## Endpoint index

| Method | Path | Role |
|--------|------|------|
| `POST` | `/api/v1/auth/login` | public |
| `POST` | `/api/v1/auth/logout` | any |
| `GET` | `/api/v1/me` | auth |
| `GET` | `/api/v1/home` | child |
| `GET` | `/api/v1/c/{qr_token}` | child |
| `POST` | `/api/v1/c/{qr_token}/complete` | child |
| `GET` | `/api/v1/achievements` | child |
| `GET` | `/api/v1/today` | parent |
| `GET` | `/api/v1/history` | parent |
| `GET`/`POST` | `/api/v1/chores` | parent |
| `GET`/`PATCH`/`DELETE` | `/api/v1/chores/{id}` | parent |
| `POST` | `/api/v1/chores/{id}/activate` | parent |
| `POST` | `/api/v1/chores/{id}/deactivate` | parent |
| `GET` | `/api/v1/chores/{id}/qr` | parent |
| `GET` | `/api/v1/chores/{id}/qr.png` | parent |
| `GET` | `/api/v1/rewards` | parent |
| `PUT` | `/api/v1/rewards/bonuses` | parent |
| `POST` | `/api/v1/rewards/achievements` | parent |
| `PATCH` | `/api/v1/rewards/achievements/{id}` | parent |
| `POST` | `/api/v1/rewards/achievements/{id}/toggle` | parent |
| `GET` | `/api/v1/photos/{completion_id}` | any auth |
| `GET` | `/healthz` | public (not under `/api/v1`) |

---

## Example (curl)

```bash
# Login (child)
TOKEN=$(curl -s -X POST "$BASE_URL/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"daughter@example.com","password":"child-pass"}' \
  | jq -r .access_token)

# Who am I
curl -s "$BASE_URL/api/v1/me" -H "Authorization: Bearer $TOKEN" | jq .

# Today (child)
curl -s "$BASE_URL/api/v1/home" -H "Authorization: Bearer $TOKEN" | jq .

# Parent board
PTOKEN=$(curl -s -X POST "$BASE_URL/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"dad@example.com","password":"parent-pass"}' \
  | jq -r .access_token)
curl -s "$BASE_URL/api/v1/today" -H "Authorization: Bearer $PTOKEN" | jq .
curl -s "$BASE_URL/api/v1/chores" -H "Authorization: Bearer $PTOKEN" | jq .
```

---

## Security notes for app developers

- Use HTTPS in production; never ship `SECRET_KEY` or seed passwords in the app binary.
- Store tokens in the platform secure store; do not log them.
- Trust only server-awarded points from API responses; do not invent scores client-side.
- QR tokens are unguessable but still require a child-authenticated complete call.
- Prefer **deactivate** over **delete** unless you intend to wipe history and photo files.
