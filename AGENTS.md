# AGENTS.md — QR Chores

Guidance for AI agents and humans working in this repo. Product decisions from the design conversation are canonical here; keep this file updated when behavior changes.

## What this is

**QR Chores** is a mobile-first family web app: parents manage **one or more children** and chores; each chore has a **stable QR code** (reused every day) and is **assigned to one child**. That child scans the code on their phone to confirm completion (with photo rules per chore) and earns **points and achievements**.

**v1 is complete** (phases 1–5 + lint/coverage/integration tests). Prefer small, tested changes over large rewrites.

## Stack (do not change without discussion)

| Layer | Choice |
|-------|--------|
| Language / packaging | Python 3.12+, **uv** project |
| Web framework | **FastAPI** |
| UI | Server-rendered **Jinja2** (mobile-first); no separate SPA for v1 |
| ORM / migrations | SQLAlchemy 2 async + **Alembic** |
| DB | **SQLite** (`aiosqlite`) locally; **Cloud SQL Postgres** (`asyncpg`) in production |
| Photos | Local disk in dev; **GCS** in prod — DB stores only `photo_object_key` |
| QR codes | **segno** (PNG, error correction M) |
| Lint / format | **ruff** |
| Tests | **pytest** + **pytest-asyncio** + **pytest-cov** (≥ 90%) |
| Deploy | **Docker** → **Google Cloud Run** (see `docs/DEPLOY.md`) |

## Roles & auth

- **Normal login** (username + password; often email-shaped, no mailbox verification), session cookie (HTTP-only, signed).
- Roles:
  - **`parent`** — Dad and Mom each have their own account. Manage **children**, chores (per assignee), QRs, rewards; track status.
  - **`child`** — One or more kids per parent. Complete **their** assigned chores; see points/achievements.
- QR URLs use unguessable tokens but **still require the assigned child’s login** before complete.
- Parent routes require `role=parent`. Complete flow requires `role=child` and matching assignee.

## Product rules (canonical)

1. **One QR per chore, stable forever** while the chore is active. Token does **not** rotate daily. Encode: `{BASE_URL}/c/{qr_token}`.
2. **Chores have due times** (local wall clock in `APP_TIMEZONE`). Completing after due is still allowed → marked **`late`**. On-time / early can drive bonuses and achievements.
3. **Photo policy is per-chore:** `required` | `optional` | `none`.
4. **No daily wipe of the chore list.** Each calendar day is an *instance* of scheduled chores. Completions are one-per-chore-per-local-date.
5. **Points & achievements** are configured by parents and **awarded automatically** on completion. Celebration UI should feel fun for a **16-year-old** (clean, bold, slightly hype — not childish cartoon, not corporate).
6. **Double-complete same day is blocked.** Show “already done” with timestamp/photo.
7. **Deactivate** stops a QR without losing history; **delete** permanently removes chore + completions + photo files.
8. **Notifications (SMS/push) are out of scope for v1.**
9. **Multi-child:** parents manage children under **Children** (`/children`); each chore has one **assignee** child; siblings cannot complete each other’s QR chores.

### Timing (v1 defaults)

- App timezone: env `APP_TIMEZONE` (default `America/Chicago`).
- `on_time`: at or before due time (+ `on_time_grace_minutes`, default 15).
- `early`: more than `early_window_minutes` before due (default 60).
- `late`: after due + grace.
- Late allowed **same calendar day**.

### Points & achievements

- Base points on the chore (once per day when completed).
- Timing bonuses from `app_settings` keys: `early_bonus_points`, `on_time_bonus_points`, `late_bonus_points` (parent-editable on `/rewards`).
  - **Early** and **on-time** bonuses are non-negative.
  - **Late** bonus may be **negative** (a late penalty, e.g. `-2`). Zero means no late adjustment. Applied via `PointLedger` like other timing bonuses.
- Achievement criteria: `streak_days`, `complete_on_time_count`, `complete_early_count`, `total_completions`, `photo_completions`.
- Always record points in **`PointLedger`** (sum = balance); do not trust the client for awards.

### Celebration UX (child)

- After complete: points breakdown, confetti/motion (respect `prefers-reduced-motion`), achievement unlock cards, and synthesized Web Audio sound effects (standard completion chime, triumphant achievement unlock fanfare, and high-energy sparkle flourish for early completion).
- Mobile-first: large type, thumb-friendly CTA, dark mode via system preference.

### Photos

- Bytes live **outside** the DB (local path or GCS object).
- Key shape: `completions/{chore_id}/{YYYY-MM-DD}/{uuid}.{ext}`.
- Validate with **magic bytes** (JPEG / PNG / WebP); enforce `PHOTO_MAX_BYTES`.
- Serve only via authenticated `GET /photos/{completion_id}`.

## Core user flows

### Parent

Login → **Today** board → **Children** (add/edit/activate/deactivate) → **Chores** (CRUD with **assignee**, deactivate/delete, QR, print) → **Rewards** (timing bonuses + achievements) → **History** (completions + photos).

### Child (QR)

Scan QR → `GET /c/{token}` → login if needed (preserve `next`) → must be the **assignee** → confirm (name, due, late?, photo) → `POST` complete → celebration (points + unlocks).

### Child (home)

Login → today’s assigned chores (pending, done, or late) + points (total balance + points change today) + achievements. Opening a chore or scanning its QR both go to `/c/{token}`; only the assignee can complete it.

## Routes

| Route | Role | Purpose |
|-------|------|---------|
| `/login` | All | Auth |
| `/` | Role redirect | Parent dashboard or child home |
| `/today` | Parent | Live status board (chores for this parent’s children) |
| `/history` | Parent | Recent completions + photos |
| `/children` | Parent | List / add / edit / activate / deactivate children |
| `/children/new` | Parent | Create child account |
| `/children/{id}/edit` | Parent | Edit child profile / password |
| `/chores` | Parent | List / create / edit / activate / deactivate (per assignee) |
| `/chores/{id}/delete` | Parent | Confirm + hard delete |
| `/chores/{id}/qr` | Parent | QR page |
| `/chores/{id}/qr.png` | Parent | QR PNG |
| `/print/qrs` | Parent | Sticker print sheet |
| `/rewards` | Parent | Timing bonuses + achievements CRUD |
| `/home` | Child | Today + points + recent unlocks |
| `/c/{token}` | Child | Confirm + photo + complete |
| `/me/achievements` | Child | Achievement collection / progress |
| `/photos/{completion_id}` | Logged-in | Stream proof photo |
| `/api/v1/*` | Auth (Bearer / session) | **Internal** JSON API for native apps — full surface in `docs/API.md` (not end-user Help) |
| `/mcp` | Public (MCP clients) | FastMCP streamable HTTP (proxied by nginx → process on `:8001`); tools call in-container API |
| `/health`, `/healthz` | Public | Cloud Run liveness health check |

### Internal API (`/api/v1`) — agent notes

- **Audience:** native apps, automation, MCP. Family UX stays Jinja + `/help`.
- **Auth:** opaque Bearer from `POST /api/v1/auth/login` (preferred) **or** session cookie. Dual-path in `auth/deps.py`.
- **Roles:** same as HTML — parent board/children/CRUD/rewards; child home/confirm/complete/achievements (assignee-scoped); photos any auth user.
- **Domain:** thin routers under `routers/api/`; awards only in `services/`.
- **Errors:** always JSON on `/api/*` (never HTML login redirect). `401` / `403` / `404` / `422`; domain complete failures use `400` with `{ "detail": { "message", "code" } }`.
- **OpenAPI:** `/docs` + `/openapi.json` in non-production only. Bearer scheme registered for try-it-out.
- **Deferred:** login rate-limiting (document only until needed).

## Data model (conceptual)

- **User** — email (username), first_name, last_name, display_name, password_hash, role (`parent`|`child`), **parent_id** (primary managing parent). Extra parents are **child_parent_links** rows (`child_id`, `parent_id`); those parents see and manage the child too. Do not clear `parent_id` when adding one.
- **Chore** — title, description, **qr_token** (unique, stable), due_time, schedule_days, photo_policy, base_points, **early_bonus_enabled**, is_active, **assignee_user_id** (child who owns the chore)
- **ChoreCompletion** — chore_id, user_id, local_date, completed_at, timing, photo_object_key, points_awarded (base + timing bonus only; not achievement rewards); **UNIQUE (chore_id, local_date)**
- **PointLedger** — user_id, delta, reason, ref_type, ref_id (sum = balance; “points today” is ledger deltas for the local day)
- **Achievement** — title, description, icon_key, criteria_type, criteria_json, points_reward, is_active
- **UserAchievement** — user_id, achievement_id, unlocked_at; unique pair
- **AppSetting** — key/value (timing bonuses)

## Project layout

```text
qr-chores/
  pyproject.toml / uv.lock
  Dockerfile
  scripts/entrypoint.sh      # RUN_MIGRATIONS / RUN_SEED
  docs/DEPLOY.md
  docs/API.md                # Internal /api/v1 for native apps (not user Help)
  README.md / AGENTS.md
  clients/                   # First-party API clients (isolated from app)
    CONTRACT.md              # Shared method/error/fixture contract
    mock-api/                # Deterministic /api/v1 mock for client tests
    python/                  # HTTP client + qrc CLI + FastMCP (qr-chores-client)
    kotlin/                  # Android-compatible Kotlin client (JDK 21)
  src/qr_chores/
    main.py
    config.py
    db.py
    seed.py
    auth/
    models/
    schemas/                 # Pydantic models for /api/v1
    routers/
      api/                   # Internal JSON API
    services/                # qr, completion, achievements, points, storage, timeutil
    templates/
    static/
  migrations/
  tests/                     # unit + HTTP tests
    integration/             # multi-step flows (@pytest.mark.integration)
```

## Config (env)

**Document every config env var in `.env.example`.** When you add or change a setting in `config.py`, `scripts/entrypoint.sh`, Docker/nginx, MCP, or client tooling that is controlled by the environment, update `.env.example` in the same change (name, purpose, type/default, and a commented example). Keep this table and `.env.example` in sync; `.env.example` is the annotated source of truth for operators.

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLite (dev) / Postgres (prod) |
| `SECRET_KEY` | Sessions / signing — **never ship the default** with HTTPS, Postgres, or `ENVIRONMENT=production` |
| `ENVIRONMENT` | `development` (default) or `production` (disables OpenAPI `/docs`) |
| `APP_TIMEZONE` | Local day boundary + due times |
| `BASE_URL` | Canonical URL in QR codes — **must stay stable** after printing stickers |
| `PHOTO_STORAGE` | `local` or `gcs` |
| `PHOTO_LOCAL_DIR` | Local upload root (dev) |
| `GCS_BUCKET` | Bucket when `PHOTO_STORAGE=gcs` |
| `PHOTO_MAX_BYTES` | Max upload size (default 5 MB); enforced while reading the upload stream |
| `PORT` | Cloud Run listens on `8080` |
| `RUN_MIGRATIONS` / `RUN_SEED` | Docker entrypoint flags |
| `ADMIN_API_KEY` | Optional internal registration API key (not family-facing UX) |
| `QR_CHORES_EMAIL` / `QR_CHORES_PASSWORD` | Optional MCP auto-login |
| `MCP_TRANSPORT` / `MCP_HOST` / `MCP_PORT` / `MCP_PATH` | FastMCP HTTP in Docker (default `http` / `127.0.0.1` / `8001` / `/mcp`) |
| `LOG_LEVEL` | App + MCP log level (default `INFO`) |
| `SYSLOG_SERVER` | Optional `host` or `host:port` (UDP, default 514). When set, **nginx**, **FastAPI**, and **MCP** dual-write logs to that rsyslog/syslogd in addition to stdout/stderr |

Local default port: **8765** (8000 is often taken).

### Security invariants (keep these)

- Login `next` must be a **single-slash relative path** only (`_safe_next_url`). Block `//`, `///`, schemes, netloc, backslashes, and control characters.
- Local photo keys: resolve under the upload root with `Path.is_relative_to`; reject `..` path segments (do not use `str.startswith` for containment).
- Photo uploads: stream with a running byte count; never `read()` unbounded into memory before the size check.
- Default `SECRET_KEY` (`dev-only-change-me`) is allowed only for local SQLite + non-HTTPS `BASE_URL` + non-production `ENVIRONMENT`.
- Production (`ENVIRONMENT=production`): OpenAPI docs disabled.
- Photo storage backends are cached (`get_photo_storage`); tests that change `PHOTO_*` should call `clear_photo_storage_cache()`.

## Implementation status

1. Skeleton & deploy path ✅  
2. Chores + QR ✅  
2.5. Chore delete ✅  
3. Photos ✅  
4. Points & achievements ✅  
5. Polish + deploy docs ✅  
6. Lint, coverage (≥ 90%), unit + integration tests ✅  
7. Security hardening (redirects, photo paths, upload caps, prod guards) ✅  
8. Internal `/api/v1` (auth, child, parent, rewards, photos) ✅ — see `docs/API.md`
9. Client libraries (`clients/python` FastMCP + **`qrc` CLI** + `clients/kotlin`) + shared mock-api ✅ — see `clients/`
10. Multi-child (Children UI/API, per-chore assignee, sibling isolation) ✅

## Quality gates (required)

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q                 # includes coverage fail-under=90
```

When changing clients:

```bash
cd clients/mock-api && uv run ruff check src tests && uv run pytest -q
cd clients/python && uv run ruff check src tests && uv run ruff format --check src tests && uv run pytest -q
cd clients/kotlin && ./gradlew test integrationTest koverVerify   # JDK 21
```

CI (`.github/workflows/ci.yml`) runs app lint/tests/Docker **and** mock-api / Python client / Kotlin client jobs.

When adding features:

- Put domain logic in `services/`; keep routers thin.
- Add unit tests for pure logic; HTTP/integration tests for flows that cross auth + DB + storage.
- Prefer `pytest.mark.integration` for multi-step parent/child scenarios.
- Do not lower the coverage floor without discussion.

### Keep the stack in sync (required)

Any change that adds or changes product behavior must update **all** of the following that apply — not just the server or a single UI path:

| Layer | What to update |
|-------|----------------|
| **App / API** | HTML routes and/or `/api/v1` (routers, schemas, services); Alembic if schema changes |
| **Client libraries** | `clients/python` (HTTP client + `qrc` CLI + FastMCP tools) and `clients/kotlin` — same method/DTO coverage; update `clients/CONTRACT.md` |
| **Mocks & tests** | App tests under `tests/`; shared mock under `clients/mock-api`; unit + integration tests for each client library |
| **Developer docs** | `docs/API.md`, `AGENTS.md`, package READMEs under `clients/`, deploy notes if needed |
| **User docs** | `docs/USER.md` and in-app Help (`/help`) when family-facing behavior changes |

Do not ship an API-only or library-only change that leaves the other surfaces stale.

### Definition of done

Work is **not** done until the relevant quality gates pass **locally** (and CI when pushing):

```bash
# App
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q

# Client mock (if clients/ touched)
cd clients/mock-api && uv run ruff check src tests && uv run pytest -q

# Python client (if clients/python touched)
cd clients/python && uv run ruff check src tests && uv run ruff format --check src tests && uv run pytest -q

# Kotlin client (if clients/kotlin touched)
cd clients/kotlin && ./gradlew test koverVerify
```

Fix failures before declaring the task complete, opening a PR as ready, or asking for review. “Implemented but untested” is not done.

## Coding conventions

- Mobile-first templates; large touch targets (~44px+); status chips for Pending / Done / Late.
- QR generation: high contrast, error correction M (`segno`).
- Never trust client content-type alone for photos.
- Constant-time password verify (`pwdlib` / argon2).
- No secrets in the repo; use env / Secret Manager.
- Cloud Run is **stateless**: durable data = Postgres + GCS only.
- Prefer Alembic migrations over ad-hoc schema edits.
- Server-side award logic only (never trust the client for points).

## Security reminders

- QR tokens: `secrets.token_urlsafe(16+)`, not sequential IDs.
- Parent vs child authorization on every mutating route.
- Photos: authenticated access only; magic-byte type sniff; size cap on read.
- Path traversal protection in local photo storage keys (`is_relative_to`, no `..` segments).
- Open-redirect hardening on login `next` (relative paths only).
- Strong `SECRET_KEY` required for HTTPS / Postgres / production.
- Every response gets `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a `script-src 'self'` CSP (`security_headers.py`); `Strict-Transport-Security` is added only when `BASE_URL` is `https://`.

## Out of scope (v1)

- Push/SMS notifications  
- Points shop / redemption  
- Public self-serve signup for new households  
- Native mobile apps  
- OAuth (password accounts only for now)  
- Parent “mark done for them” override  

## When unsure

Default to: mobile-first child UX, stable QR tokens, server-side awards, and Cloud Run–friendly stateless design. Update this file when product rules change.
