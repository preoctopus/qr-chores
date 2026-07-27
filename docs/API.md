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

## Errors

- All `/api/*` responses use JSON error bodies (never HTML login redirects).
- Prefer standard HTTP status codes: `401`, `403`, `404`, `400`, `422` (validation).

---

## Example (curl)

```bash
# Login
TOKEN=$(curl -s -X POST "$BASE_URL/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"daughter@example.com","password":"child-pass"}' \
  | jq -r .access_token)

# Who am I
curl -s "$BASE_URL/api/v1/me" -H "Authorization: Bearer $TOKEN" | jq .

# Today (child)
curl -s "$BASE_URL/api/v1/home" -H "Authorization: Bearer $TOKEN" | jq .
```

---

## Roadmap (not in this version)

Parent board, chore CRUD, rewards, and photo fetch under `/api/v1` are planned as follow-ups to issue #27. HTML parent routes remain canonical until then.

---

## Security notes for app developers

- Use HTTPS in production; never ship `SECRET_KEY` or seed passwords in the app binary.
- Store tokens in the platform secure store; do not log them.
- Trust only server-awarded points from API responses; do not invent scores client-side.
- QR tokens are unguessable but still require a child-authenticated complete call.
