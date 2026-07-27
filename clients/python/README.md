# qr-chores-client

Typed Python HTTP client and **FastMCP** server for the QR Chores internal JSON API (`/api/v1`).

See [../CONTRACT.md](../CONTRACT.md) and [../../docs/API.md](../../docs/API.md).

## Install

From this directory (editable + dev tools + mock-api for tests):

```bash
cd clients/python
uv sync --extra dev
```

As a dependency elsewhere:

```bash
uv add --editable path/to/qr-chores/clients/python
# or: pip install path/to/qr-chores/clients/python
```

Requires **Python 3.12+**.

## Async client

```python
import asyncio
from qr_chores_client import QrChoresClient

async def main() -> None:
    async with QrChoresClient("http://127.0.0.1:8765") as client:
        token = await client.login("child@example.com", "child-pass")
        print(token.user.display_name, token.access_token)

        me = await client.get_me()
        home = await client.get_home()
        print(home.points_balance, home.done_count, "/", home.total_count)

        await client.logout()

asyncio.run(main())
```

`login` stores `access_token` and sends `Authorization: Bearer …` on subsequent calls.

### Complete chore with photo

```python
async with QrChoresClient(base_url) as client:
    await client.login("child@example.com", "child-pass")
    with open("proof.jpg", "rb") as f:
        photo = f.read()
    result = await client.complete_chore(
        "qr-photo-required",
        photo=photo,
        photo_filename="proof.jpg",
        photo_content_type="image/jpeg",
    )
    print(result.points.total, result.unlocks)
```

### Parent CRUD

```python
from qr_chores_client.models import ChoreCreate, ChoreUpdate, AchievementCreate

async with QrChoresClient(base_url) as client:
    await client.login("parent@example.com", "parent-pass")

    today = await client.get_today()
    chores = await client.list_chores(include_inactive=True)

    chore = await client.create_chore(
        ChoreCreate(
            title="Vacuum living room",
            due_time="18:00:00",
            photo_policy="optional",
            base_points=15,
        )
    )
    await client.update_chore(chore.id, ChoreUpdate(base_points=20))
    qr = await client.get_qr_info(chore.id)
    png = await client.get_qr_png(chore.id)

    rewards = await client.get_rewards()
    await client.update_bonuses(
        early_bonus_points=5,
        on_time_bonus_points=2,
        late_bonus_points=0,
    )
    await client.create_achievement(
        AchievementCreate(
            title="Early bird",
            criteria_type="complete_early_count",
            threshold=5,
            points_reward=25,
        )
    )

    await client.deactivate_chore(chore.id)
    # await client.delete_chore(chore.id)  # hard delete
```

## Sync wrapper

`SyncQrChoresClient` mirrors the async methods via `asyncio.run`. **Do not use it from inside an already-running event loop** (use `QrChoresClient` instead).

```python
from qr_chores_client import SyncQrChoresClient

with SyncQrChoresClient("http://127.0.0.1:8765") as client:
    client.login("parent@example.com", "parent-pass")
    print(client.get_today().board)
```

## Errors

| Status | Exception |
|--------|-----------|
| 401 | `AuthError` |
| 403 | `ForbiddenError` |
| 404 | `NotFoundError` |
| 400 | `DomainError` (`.code`, `.message`) |
| 422 | `ValidationError` (`.errors`) |
| other | `ApiError` |

```python
from qr_chores_client import DomainError

try:
    await client.complete_chore("qr-photo-required")
except DomainError as e:
    if e.code == "photo_required":
        ...
```

## FastMCP server

Run over stdio:

```bash
export QR_CHORES_BASE_URL=http://127.0.0.1:8765
export QR_CHORES_EMAIL=parent@example.com
export QR_CHORES_PASSWORD=parent-pass

python -m qr_chores_client
# or: qr-chores-client
# or: uv run python -m qr_chores_client
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `QR_CHORES_BASE_URL` | API origin (default `http://127.0.0.1:8765`) |
| `QR_CHORES_EMAIL` | Auto-login email on server start / tool use |
| `QR_CHORES_PASSWORD` | Auto-login password |

You can also call the `login` tool with explicit credentials.

Binary responses (`get_qr_png`, `get_photo`) are returned as JSON:

```json
{
  "encoding": "base64",
  "content_type": "application/octet-stream",
  "data": "…",
  "size": 123
}
```

`complete_chore` accepts optional `photo_base64`.

### MCP tools

| Tool | API |
|------|-----|
| `login` | `POST /auth/login` |
| `logout` | `POST /auth/logout` |
| `get_me` | `GET /me` |
| `get_home` | `GET /home` |
| `get_confirm` | `GET /c/{qr_token}` |
| `complete_chore` | `POST /c/{qr_token}/complete` |
| `get_achievements` | `GET /achievements` |
| `get_today` | `GET /today` |
| `get_history` | `GET /history` |
| `list_chores` | `GET /chores` |
| `create_chore` | `POST /chores` |
| `get_chore` | `GET /chores/{id}` |
| `update_chore` | `PATCH /chores/{id}` |
| `delete_chore` | `DELETE /chores/{id}` |
| `activate_chore` | `POST /chores/{id}/activate` |
| `deactivate_chore` | `POST /chores/{id}/deactivate` |
| `get_qr_info` | `GET /chores/{id}/qr` |
| `get_qr_png` | `GET /chores/{id}/qr.png` |
| `get_rewards` | `GET /rewards` |
| `update_bonuses` | `PUT /rewards/bonuses` |
| `create_achievement` | `POST /rewards/achievements` |
| `update_achievement` | `PATCH /rewards/achievements/{id}` |
| `toggle_achievement` | `POST /rewards/achievements/{id}/toggle` |
| `get_photo` | `GET /photos/{completion_id}` |

## Testing against mock-api

This package depends on `qr-chores-mock-api` (path `../mock-api`) for integration tests. Tests prefer **httpx ASGI transport** (no live port).

Fixture accounts:

| Role | Email | Password | Token |
|------|-------|----------|-------|
| parent | `parent@example.com` | `parent-pass` | `parent-token` |
| child | `child@example.com` | `child-pass` | `child-token` |

Optional live mock:

```bash
cd clients/mock-api
uv run uvicorn qr_chores_mock_api.app:app --host 127.0.0.1 --port 18080
```

## Quality gates

```bash
cd clients/python
uv sync --extra dev
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q
```

Coverage fail-under is **90%** on `qr_chores_client`.

## Package layout

```text
clients/python/
  src/qr_chores_client/
    client.py       # async QrChoresClient
    sync_client.py  # SyncQrChoresClient
    models.py       # pydantic v2 models
    errors.py
    mcp_server.py
    __main__.py
  tests/
    unit/           # respx
    integration/    # mock-api ASGI
```
