# AGENTS.md — QR Chores

Guidance for AI agents and humans working in this repo. Product decisions from the design conversation are canonical here; keep this file updated when behavior changes.

## What this is

**QR Chores** is a mobile-first family web app: parents manage chores for their daughter; each chore has a **stable QR code** (reused every day). She scans the code on her phone to confirm completion (with photo rules per chore) and earns **points and achievements**.

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
| Tests | **pytest** + **pytest-asyncio** + **pytest-cov** (≥ 75%) |
| Deploy | **Docker** → **Google Cloud Run** (see `docs/DEPLOY.md`) |

## Roles & auth

- **Normal login** (email + password), session cookie (HTTP-only, signed).
- Roles:
  - **`parent`** — Dad and Mom each have their own account. Manage chores, QRs, rewards; track status.
  - **`child`** — Daughter. Complete chores, see points/achievements.
- QR URLs use unguessable tokens but **still require child login** before complete.
- Parent routes require `role=parent`. Complete flow requires `role=child`.

## Product rules (canonical)

1. **One QR per chore, stable forever** while the chore is active. Token does **not** rotate daily. Encode: `{BASE_URL}/c/{qr_token}`.
2. **Chores have due times** (local wall clock in `APP_TIMEZONE`). Completing after due is still allowed → marked **`late`**. On-time / early can drive bonuses and achievements.
3. **Photo policy is per-chore:** `required` | `optional` | `none`.
4. **No daily wipe of the chore list.** Each calendar day is an *instance* of scheduled chores. Completions are one-per-chore-per-local-date.
5. **Points & achievements** are configured by parents and **awarded automatically** on completion. Celebration UI should feel fun for a **16-year-old** (clean, bold, slightly hype — not childish cartoon, not corporate).
6. **Double-complete same day is blocked.** Show “already done” with timestamp/photo.
7. **Deactivate** stops a QR without losing history; **delete** permanently removes chore + completions + photo files.
8. **Notifications (SMS/push) are out of scope for v1.**
9. **UI assumes one child for v1**; data model may allow more later.

### Timing (v1 defaults)

- App timezone: env `APP_TIMEZONE` (default `America/Chicago`).
- `on_time`: at or before due time (+ `on_time_grace_minutes`, default 15).
- `early`: more than `early_window_minutes` before due (default 60).
- `late`: after due + grace.
- Late allowed **same calendar day**.

### Points & achievements

- Base points on the chore (once per day when completed).
- Timing bonuses from `app_settings` keys: `early_bonus_points`, `on_time_bonus_points`, `late_bonus_points` (parent-editable on `/rewards`).
- Achievement criteria: `streak_days`, `complete_on_time_count`, `complete_early_count`, `total_completions`, `photo_completions`.
- Always record points in **`PointLedger`** (sum = balance); do not trust the client for awards.

### Celebration UX (child)

- After complete: points breakdown, confetti/motion (respect `prefers-reduced-motion`), achievement unlock cards.
- Mobile-first: large type, thumb-friendly CTA, dark mode via system preference.

### Photos

- Bytes live **outside** the DB (local path or GCS object).
- Key shape: `completions/{chore_id}/{YYYY-MM-DD}/{uuid}.{ext}`.
- Validate with **magic bytes** (JPEG / PNG / WebP); enforce `PHOTO_MAX_BYTES`.
- Serve only via authenticated `GET /photos/{completion_id}`.

## Core user flows

### Parent

Login → **Today** board → **Chores** (CRUD, deactivate/delete, QR, print) → **Rewards** (timing bonuses + achievements) → **History** (completions + photos).

### Child (QR)

Scan QR → `GET /c/{token}` → login if needed (preserve `next`) → confirm (name, due, late?, photo) → `POST` complete → celebration (points + unlocks).

### Child (home)

Login → today’s list + total points → tap chore → same confirm path as QR → `/me/achievements` for progress.

## Routes

| Route | Role | Purpose |
|-------|------|---------|
| `/login` | All | Auth |
| `/` | Role redirect | Parent dashboard or child home |
| `/today` | Parent | Live status board |
| `/history` | Parent | Recent completions + photos |
| `/chores` | Parent | List / create / edit / activate / deactivate |
| `/chores/{id}/delete` | Parent | Confirm + hard delete |
| `/chores/{id}/qr` | Parent | QR page |
| `/chores/{id}/qr.png` | Parent | QR PNG |
| `/print/qrs` | Parent | Sticker print sheet |
| `/rewards` | Parent | Timing bonuses + achievements CRUD |
| `/home` | Child | Today + points + recent unlocks |
| `/c/{token}` | Child | Confirm + photo + complete |
| `/me/achievements` | Child | Achievement collection / progress |
| `/photos/{completion_id}` | Logged-in | Stream proof photo |
| `/healthz` | Public | Cloud Run health |

## Data model (conceptual)

- **User** — email, display_name, password_hash, role (`parent`|`child`)
- **Chore** — title, description, **qr_token** (unique, stable), due_time, schedule_days, photo_policy, base_points, is_active
- **ChoreCompletion** — chore_id, user_id, local_date, completed_at, timing, photo_object_key, points_awarded; **UNIQUE (chore_id, local_date)**
- **PointLedger** — user_id, delta, reason, ref_type, ref_id
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
  README.md / AGENTS.md
  src/qr_chores/
    main.py
    config.py
    db.py
    seed.py
    auth/
    models/
    routers/
    services/                # qr, completion, achievements, points, storage, timeutil
    templates/
    static/
  migrations/
  tests/                     # unit + HTTP tests
    integration/             # multi-step flows (@pytest.mark.integration)
```

## Config (env)

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
6. Lint, coverage (≥ 75%), unit + integration tests ✅  
7. Security hardening (redirects, photo paths, upload caps, prod guards) ✅  

## Quality gates (required)

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q                 # includes coverage fail-under=75
```

CI (`.github/workflows/ci.yml`) runs lint → format → tests+coverage → Docker build.

When adding features:

- Put domain logic in `services/`; keep routers thin.
- Add unit tests for pure logic; HTTP/integration tests for flows that cross auth + DB + storage.
- Prefer `pytest.mark.integration` for multi-step parent/child scenarios.
- Do not lower the coverage floor without discussion.

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

## Out of scope (v1)

- Push/SMS notifications  
- Points shop / redemption  
- Multi-child first-class UX  
- Native mobile apps  
- OAuth (password accounts only for now)  
- Parent “mark done for her” override  

## When unsure

Default to: mobile-first child UX, stable QR tokens, server-side awards, and Cloud Run–friendly stateless design. Update this file when product rules change.
