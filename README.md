# QR Chores

A mobile-first family chore app. Parents manage a chore list; each chore gets a **stable QR code**. Your daughter scans the code on her phone to mark the chore done (with optional or required photo proof), and earns **points and achievements** along the way.

Built as a **Python** app with **uv**, **FastAPI**, and **Docker**, meant to run on **Google Cloud Run**.

| Docs | |
|------|--|
| **Using QR Chores** (parents & child) | [docs/USER.md](./docs/USER.md) · in-app at `/help` |
| **Internal JSON API** (native apps / MCP) | [docs/API.md](./docs/API.md) · `/api/v1` |
| **Client libraries** (Python FastMCP + Kotlin) | [clients/](./clients/) · [CONTRACT](./clients/CONTRACT.md) |
| Product & coding rules for agents | [AGENTS.md](./AGENTS.md) |
| Cloud Run + Cloud SQL + GCS deploy | [docs/DEPLOY.md](./docs/DEPLOY.md) |

**Status:** v1 complete — features, polish, lint, coverage, and integration tests are on `main` with green CI.

---

## Who it’s for

| Role | People | What they do |
|------|--------|----------------|
| **Parent** | Mom and Dad (separate logins) | Add/edit/delete chores, print QR stickers, configure points & achievements, track today + history |
| **Child** | Daughter | Log in, scan QR / open list, confirm + photo, earn points and unlock achievements |

---

## How it works

### Stable QR codes

- Each chore has **one QR code** reused every day (print stickers once).
- URL shape: `{BASE_URL}/c/{token}`.
- Completing still requires the child to be **logged in**.
- **Keep `BASE_URL` stable** before printing stickers.

### Completing a chore

1. Scan the QR (or tap the chore on home).
2. Confirm page: name, due time, late indicator.
3. Photo when the chore requires/allows it (JPEG / PNG / WebP).
4. Tap **I did it** → early / on time / late, points, achievements, celebration.

### Due times

- Chores have due times; the list is not wiped at midnight.
- Late completions are allowed and labeled.
- Timezone via `APP_TIMEZONE` (default `America/Chicago`).

### Points & achievements

- Base points per chore + parent-configured timing bonuses.
- Achievements auto-unlock (streaks, on-time, photos, totals, etc.).
- Parents manage everything under **Rewards**.

---

## Tech stack

| Piece | Choice |
|-------|--------|
| Package manager | [uv](https://github.com/astral-sh/uv) |
| Framework | FastAPI + Jinja2 (mobile-first) |
| Database | **SQLite** (`aiosqlite`) locally · **Postgres** (`asyncpg`) on Cloud Run |
| Photos | **Local files** (dev) or **GCS** objects (prod) — DB stores only a key |
| Lint / format | [ruff](https://docs.astral.sh/ruff/) |
| Tests | pytest + coverage (≥ 75%) |
| Deploy | Docker → Google Cloud Run |
| CI | GitHub Actions: ruff → pytest+cov → Docker build |

---

## Local development

### Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

### Setup

```bash
uv sync --extra dev
cp .env.example .env   # optional; defaults work for local SQLite
```

### Seed users

```bash
uv run qr-chores-seed
```

Creates (idempotent):

| Email | Role | Default password |
|-------|------|------------------|
| `dad@example.com` | parent | `parent-pass` |
| `mom@example.com` | parent | `parent-pass` |
| `daughter@example.com` | child | `child-pass` |

Also seeds default achievements and timing bonus settings.

### Run the app

```bash
uv run uvicorn qr_chores.main:app --reload --port 8765
```

Open http://127.0.0.1:8765

> Prefer **8765** (or any free port). Port 8000 is often used by other local apps.

### Internal JSON API (`/api/v1`)

For native apps, scripts, and MCP — **not** the family Help page. Full reference: [docs/API.md](./docs/API.md).

In development, interactive OpenAPI is at http://127.0.0.1:8765/docs (disabled when `ENVIRONMENT=production`).

```bash
# Login → bearer token
TOKEN=$(curl -s -X POST http://127.0.0.1:8765/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"daughter@example.com","password":"child-pass"}' \
  | jq -r .access_token)

curl -s http://127.0.0.1:8765/api/v1/home \
  -H "Authorization: Bearer $TOKEN" | jq .
```

Auth is **Bearer** (preferred for native) or the same session cookie as the HTML UI. Roles match the app: child complete, parent board/CRUD/rewards.

### Tests, lint, and coverage

```bash
# Lint + format check
uv run ruff check src tests
uv run ruff format --check src tests

# Unit + integration tests with coverage (fails under 75%)
uv run pytest -q

# Integration tests only
uv run pytest -q -m integration
```

CI runs the same gates on every push/PR to `main`.

### Migrations

Tables auto-create on startup for local convenience. Production-style:

```bash
uv run alembic upgrade head
```

---

## Docker

```bash
docker build -t qr-chores .
docker run --rm -p 8080:8080 \
  -e SECRET_KEY=dev-secret \
  -e ENVIRONMENT=development \
  -e DATABASE_URL=sqlite+aiosqlite:////tmp/qr_chores.db \
  -e BASE_URL=http://127.0.0.1:8080 \
  -e PHOTO_STORAGE=local \
  -e PHOTO_LOCAL_DIR=/tmp/uploads \
  -e RUN_SEED=1 \
  qr-chores
```

| Env | Effect |
|-----|--------|
| `RUN_MIGRATIONS=1` | Entrypoint runs `alembic upgrade head` |
| `RUN_SEED=1` | Seeds users + default achievements |

Health: `GET /healthz`

Full production steps: **[docs/DEPLOY.md](./docs/DEPLOY.md)**.

---

## Database & image storage

### Database

- ORM: **SQLAlchemy 2.x async** + **Alembic** migrations.
- **Local / tests:** SQLite  
  `DATABASE_URL=sqlite+aiosqlite:///./data/qr_chores.db` (or `:memory:` in CI).
- **Production (Cloud Run):** Postgres on Cloud SQL  
  `DATABASE_URL=postgresql+asyncpg://USER:PASS@/DB?host=/cloudsql/INSTANCE`
- Prefer `alembic upgrade head` in prod (`RUN_MIGRATIONS=1` in the Docker entrypoint).

### Images (chore proof photos)

- Completions store a **`photo_object_key`** string (not image bytes in the DB).
- **Dev:** `PHOTO_STORAGE=local` → files under `PHOTO_LOCAL_DIR`  
  e.g. `./data/uploads/completions/{chore_id}/{date}/{uuid}.png`
- **Prod:** `PHOTO_STORAGE=gcs` + `GCS_BUCKET` → same key in the bucket.
- Serving: authenticated `GET /photos/{completion_id}`.
- Types: JPEG / PNG / WebP (magic-byte checked), max `PHOTO_MAX_BYTES` (default 5 MB).

---

## Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SECRET_KEY` | Session signing | `dev-only-change-me` (local SQLite only) |
| `ENVIRONMENT` | `development` or `production` | `development` |
| `DATABASE_URL` | SQLAlchemy async URL | `sqlite+aiosqlite:///./data/qr_chores.db` |
| `APP_TIMEZONE` | Day boundary / due times | `America/Chicago` |
| `BASE_URL` | Canonical URL for QR links | `http://127.0.0.1:8765` |
| `PORT` | Listen port (Cloud Run) | `8080` in image |
| `SEED_PARENT_PASSWORD` | Seed script | `parent-pass` |
| `SEED_CHILD_PASSWORD` | Seed script | `child-pass` |
| `PHOTO_STORAGE` | `local` or `gcs` | `local` |
| `PHOTO_LOCAL_DIR` | Local upload directory | `./data/uploads` |
| `GCS_BUCKET` | Bucket when `PHOTO_STORAGE=gcs` | _(empty)_ |
| `PHOTO_MAX_BYTES` | Max upload size (enforced while reading) | `5242880` (5 MB) |
| `RUN_MIGRATIONS` | Docker entrypoint migrates | `0` |
| `RUN_SEED` | Docker entrypoint seeds | `0` |

### Security notes

- **`SECRET_KEY`:** The default `dev-only-change-me` is rejected when `BASE_URL` is HTTPS, `DATABASE_URL` is Postgres, or `ENVIRONMENT=production`. Always set a strong random secret in Secret Manager for Cloud Run.
- **`ENVIRONMENT=production`:** Disables FastAPI `/docs`, `/redoc`, and `/openapi.json`.
- **Login `next`:** Only same-origin relative paths are allowed (blocks `//` / `///` open redirects).
- **Photos:** Magic-byte type check; size capped while streaming the upload; local keys reject path traversal (including prefix-sibling escapes).
- **Response headers:** `nosniff`, `Referrer-Policy`, `X-Frame-Options`, and a CSP (`script-src 'self'`) on every response; `Strict-Transport-Security` when `BASE_URL` is HTTPS.

---

## Project layout

```text
qr-chores/
├── src/qr_chores/           # FastAPI application
│   ├── auth/
│   ├── models/
│   ├── schemas/             # /api/v1 Pydantic models
│   ├── routers/
│   │   └── api/             # /api/v1 JSON API
│   ├── services/
│   ├── templates/
│   └── static/
├── migrations/              # Alembic
├── scripts/entrypoint.sh
├── docs/API.md              # Internal API (native apps)
├── docs/DEPLOY.md
├── tests/
│   └── integration/         # multi-step flows
├── .github/workflows/ci.yml
├── Dockerfile
├── pyproject.toml
├── AGENTS.md
└── README.md
```

---

## Implementation roadmap

1. **Skeleton** ✅ — uv, FastAPI, Docker, auth, health, seed, CI  
2. **Chores + QR** ✅ — parent CRUD, stable tokens, QR/print, child complete  
2.5. **Chore delete** ✅ — hard delete with confirm; deactivate for soft stop  
3. **Photos** ✅ — policy, local/GCS, history  
4. **Points & achievements** ✅ — ledger, bonuses, unlocks, celebration  
5. **Polish** ✅ — print stickers, empty/error pages, deploy docs  
6. **Quality** ✅ — ruff, coverage ≥ 75%, unit + integration tests  
7. **Hardening** ✅ — open-redirect fixes, photo path safety, upload size cap, prod secret/docs guards  
8. **Internal JSON API** ✅ — `/api/v1` auth, child + parent surfaces; see [docs/API.md](./docs/API.md)

---

## License

Private family project unless otherwise noted.
