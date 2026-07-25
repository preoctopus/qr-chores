# AGENTS.md — QR Chores

Guidance for AI agents and humans working in this repo. Product decisions from the design conversation are canonical here; keep this file updated when behavior changes.

## What this is

**QR Chores** is a mobile-first family web app: parents manage chores for their daughter; each chore has a **stable QR code** (reused every day). She scans the code on her phone to confirm completion (with photo rules per chore) and earns **points and achievements**.

## Stack (do not change without discussion)

| Layer | Choice |
|-------|--------|
| Language / packaging | Python, **uv** project |
| Web framework | **FastAPI** |
| UI | Server-rendered **Jinja2** (mobile-first); light HTMX/Alpine OK; no separate SPA for v1 |
| DB | **SQLite** locally; **Cloud SQL Postgres** in production |
| Photos | Local disk in dev; **GCS** in prod |
| Deploy | **Docker** image → **Google Cloud Run** |
| Migrations | Alembic |

## Roles & auth

- **Normal login** (username/email + password), session cookie (HTTP-only).
- Roles:
  - **`parent`** — Dad and Mom each have their own account. Manage chores, QRs, rewards; track status.
  - **`child`** — Daughter. Complete chores, see points/achievements.
- QR URLs use unguessable tokens but **still require child login** before complete.
- Parent routes require `role=parent`. Complete flow requires `role=child` (parent “mark done for her” is optional later, not v1).

## Product rules (canonical)

1. **One QR per chore, stable forever** while the chore is active. Token does **not** rotate daily. Encode: `{BASE_URL}/c/{qr_token}`.
2. **Chores have due times** (local wall clock in `APP_TIMEZONE`). Completing after due is still allowed → marked **`late`**. On-time / early can drive bonuses and achievements.
3. **Photo policy is per-chore:** `required` | `optional` | `none`.
4. **No daily wipe of the chore list.** Each calendar day is an *instance* of scheduled chores. Completions are one-per-chore-per-local-date.
5. **Points & achievements** are configured by parents and **awarded automatically** on completion. Celebration UI should feel fun for a **16-year-old** (clean, bold, slightly hype — not childish cartoon, not corporate).
6. **Double-complete same day is blocked.** Show “already done” with timestamp/photo.
7. **Notifications (SMS/push) are out of scope for v1.**
8. **UI assumes one child for v1**; data model may allow more later.

### Timing (v1 defaults)

- App timezone: env `APP_TIMEZONE` (default `America/Chicago` unless configured otherwise).
- `on_time`: at or before due time (+ optional grace minutes).
- `early`: more than N minutes before due (optional window).
- `late`: after due + grace.
- Late allowed **same calendar day**; end-of-day “missed” status is optional later.

### Points & achievements (v1 criteria types)

- Base points on the chore (always once per day when completed).
- Optional timing bonuses (early / on-time / late → late may be zero bonus).
- Achievement criteria types: `streak_days`, `complete_on_time_count`, `complete_early_count`, `total_completions`, `photo_completions`.
- Record points in a **ledger** (`PointLedger`), not only a single balance field.

### Celebration UX (child)

- After complete: points count-up, confetti/motion (respect `prefers-reduced-motion`), achievement unlock cards.
- Mobile-first: large type, thumb-friendly CTA, dark mode via system preference.

## Core user flows

### Parent

Login → dashboard (today’s board) → manage chores (CRUD, due time, schedule days, photo policy, base points) → view/download/print QRs → configure rewards/achievements → optional completion history with photos.

### Child (QR)

Scan QR → `GET /c/{token}` → login if needed (preserve `next`) → confirm screen (name, due, late?, photo) → `POST` complete → celebration (points + unlocks).

### Child (home)

Login → today’s list + points + streaks/achievements → tap chore → same confirm path as QR.

## Routes (target IA)

| Route | Role | Purpose |
|-------|------|---------|
| `/login` | All | Auth |
| `/` | Role redirect | Parent dashboard or child home |
| `/chores` | Parent | List / create / edit |
| `/chores/{id}/qr` | Parent | QR image + print |
| `/print/qrs` | Parent | Batch printable sheet |
| `/rewards` | Parent | Points rules + achievements |
| `/today` | Parent | Live status board |
| `/home` | Child | Today + points + achievements |
| `/c/{token}` | Child | Confirm + photo + complete |
| `/me/achievements` | Child | Collection |
| `/healthz` | Public | Cloud Run health |

## Data model (conceptual)

- **User** — email/username, display_name, password_hash, role (`parent`|`child`)
- **Chore** — title, description, **qr_token** (unique, stable), due_time, schedule_days, photo_policy, base_points, is_active
- **ChoreCompletion** — chore_id, user_id, local_date, completed_at, timing (`early`|`on_time`|`late`), photo_object_key, points_awarded; **UNIQUE (chore_id, local_date)**
- **PointLedger** — user_id, delta, reason, ref_type, ref_id
- **Achievement** — title, description, icon_key, criteria_type, criteria_json, points_reward, is_active
- **UserAchievement** — user_id, achievement_id, unlocked_at; unique pair
- **AppSettings** — timezone, early_window_minutes, on_time_grace_minutes (or env-only for v1)

## Project layout (target)

```
qr-chores/
  pyproject.toml          # uv
  uv.lock
  Dockerfile
  .dockerignore
  README.md
  AGENTS.md
  app/
    main.py
    config.py
    db.py
    models/
    schemas/
    auth/
    routers/
    services/             # qr, completion, achievements, storage
    templates/
    static/
  migrations/             # Alembic
  tests/
```

## Config (env)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Postgres (prod) / SQLite (dev) |
| `SECRET_KEY` | Sessions / signing |
| `APP_TIMEZONE` | Local day boundary + due times |
| `BASE_URL` | Canonical URL baked into QR codes — **must stay stable** after printing stickers |
| `GCS_BUCKET` | Photo storage (prod) |
| `PORT` | Cloud Run listens on `8080` |

## Implementation phases

1. **Skeleton & deploy path** — uv, FastAPI, Docker, healthz, config, DB, Alembic, users + login, seed parents + child.
2. **Chores + QR** — parent CRUD, stable token, QR PNG/print, child home, complete without photo.
3. **Photos + timing** — photo policy, local/GCS upload, early/on_time/late, parent board + history.
4. **Points & achievements** — ledger, bonuses, auto-eval, celebration UI.
5. **Polish** — print sheet, empty/error states, tests, deploy docs.

Prefer shipping Phase 1–2 before rewards so the happy path works early.

## Coding conventions

- Prefer small, focused modules under `app/services/` for domain logic (completion, achievements, QR); keep routers thin.
- Mobile-first templates; large touch targets (~44px+); status chips for Pending / Done / Late.
- QR generation: high contrast, error correction M or Q (`segno` or `qrcode`).
- Validate photo MIME/size; never trust client content type alone.
- CSRF on form POSTs; constant-time password verify.
- Do not put secrets in the repo; use env / Secret Manager.
- Cloud Run: do not rely on local disk for durable data; use Postgres + GCS.
- Prefer Alembic migrations over ad-hoc schema edits.
- Tests should cover: one completion per chore per day, timing classification, achievement grant, auth role gates.

## Security reminders

- QR tokens: `secrets.token_urlsafe(16+)`, not sequential IDs.
- Rate-limit login when practical.
- Parent vs child authorization on every mutating route.
- Photos: authenticated access or short-lived signed URLs in prod.

## Out of scope (v1)

- Push/SMS notifications
- Points “shop” / redemption (accumulate + celebrate only unless product expands)
- Multi-child first-class UX
- Native mobile apps
- OAuth (Google login) — password accounts only for now

## When unsure

Default to: mobile-first child UX, stable QR tokens, server-side award logic (never trust the client for points), and Cloud Run–friendly stateless app design. Update this file when product rules change.
