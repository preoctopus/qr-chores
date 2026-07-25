# QR Chores

A mobile-first family chore app. Parents manage a chore list; each chore gets a **stable QR code**. Your daughter scans the code on her phone to mark the chore done (with optional or required photo proof), and earns **points and achievements** along the way.

Built as a **Python** app with **uv**, **FastAPI**, and **Docker**, meant to run on **Google Cloud Run**.

See [AGENTS.md](./AGENTS.md) for product rules and architecture for contributors/agents.

**Current status:** Phase 2 complete — chores CRUD, stable QR codes, child complete flow, parent today board.

---

## Who it’s for

| Role | People | What they do |
|------|--------|----------------|
| **Parent** | Mom and Dad (separate logins) | Add/edit chores, set due times and photo rules, print QR codes, configure points & achievements, track today’s status |
| **Child** | Daughter | Log in, scan QR codes (or open today’s list), confirm chores, attach photos when needed, collect points and achievements |

---

## How it works (product)

### Stable QR codes

- Each chore has **one QR code** reused every day (print stickers once).
- URL shape: `https://your-app/c/{token}` (Phase 2+).
- Completing still requires the child to be **logged in**.

### Completing a chore (Phase 2+)

1. Scan the QR (or tap the chore on home).
2. Confirm page: name, due time, late indicator.
3. Photo when the chore requires/allows it.
4. Tap **I did it** → early / on time / late, points, achievements, celebration.

### Due times

- Chores have due times; the list is not wiped at midnight.
- Late completions are allowed and labeled.
- Timezone via `APP_TIMEZONE` (default `America/Chicago`).

---

## Tech stack

| Piece | Choice |
|-------|--------|
| Package manager | [uv](https://github.com/astral-sh/uv) |
| Framework | FastAPI + Jinja2 (mobile-first) |
| Database | SQLite (local) · Cloud SQL Postgres (Cloud Run) |
| Photos | Local disk (dev) · GCS (prod) — later phases |
| Deploy | Docker → Google Cloud Run |
| CI | GitHub Actions (pytest + Docker build) |

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

Override with `SEED_PARENT_PASSWORD` / `SEED_CHILD_PASSWORD`.

### Run the app

```bash
uv run uvicorn qr_chores.main:app --reload --port 8765
```

Open http://127.0.0.1:8765 — log in as a parent or the child.

> Prefer **8765** (or any free port). Port 8000 is often used by other local apps.

### Tests

```bash
uv run pytest -q
```

### Migrations (optional locally)

Tables are auto-created on startup for convenience. For production-style migrations:

```bash
uv run alembic upgrade head
```

---

## Docker

```bash
docker build -t qr-chores .
docker run --rm -p 8080:8080 \
  -e SECRET_KEY=dev-secret \
  -e DATABASE_URL=sqlite+aiosqlite:////tmp/qr_chores.db \
  -e BASE_URL=http://127.0.0.1:8080 \
  qr-chores
```

Health: `GET /healthz`

---

## Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SECRET_KEY` | Session signing | `dev-only-change-me` |
| `DATABASE_URL` | SQLAlchemy async URL | `sqlite+aiosqlite:///./data/qr_chores.db` |
| `APP_TIMEZONE` | Day boundary / due times | `America/Chicago` |
| `BASE_URL` | Canonical URL for QR links | `http://127.0.0.1:8765` |
| `PORT` | Listen port (Cloud Run) | `8080` in image |
| `SEED_PARENT_PASSWORD` | Seed script | `parent-pass` |
| `SEED_CHILD_PASSWORD` | Seed script | `child-pass` |

**Keep `BASE_URL` stable** before printing QR stickers (Phase 2+).

---

## Project layout

```text
qr-chores/
├── src/qr_chores/       # FastAPI application
│   ├── auth/            # passwords, sessions, deps
│   ├── models/          # SQLAlchemy models
│   ├── routers/         # HTTP routes
│   ├── templates/       # Mobile-first HTML
│   ├── static/          # CSS / JS
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   └── seed.py
├── migrations/          # Alembic
├── tests/
├── .github/workflows/ci.yml
├── Dockerfile
├── pyproject.toml
├── AGENTS.md
└── README.md
```

---

## Implementation roadmap

1. **Skeleton** ✅ — uv, FastAPI, Docker, auth, health, seed, CI  
2. **Chores + QR** ✅ — parent CRUD, stable tokens, QR/print, child complete, timing labels  
3. **Photos** — photo rules enforced, local/GCS upload  
4. **Points & achievements** — ledger, auto-awards, celebration UI  
5. **Polish** — richer print sheet, Cloud Run deploy docs  

---

## License

Private family project unless otherwise noted.
