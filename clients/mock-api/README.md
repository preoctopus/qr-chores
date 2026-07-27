# QR Chores mock API

Deterministic FastAPI mock of `/api/v1` for client library unit/integration tests.

## Setup

```bash
cd clients/mock-api
uv sync --extra dev
```

## Run

```bash
uv run uvicorn qr_chores_mock_api.app:app --host 127.0.0.1 --port 18080
```

`GET /healthz` → `{"status":"ok"}`.

## Fixture accounts

See [../CONTRACT.md](../CONTRACT.md).

## Tests

```bash
uv run pytest -q
```

## Reset

Python: `from qr_chores_mock_api.app import reset_state`.
