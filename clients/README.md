# QR Chores client libraries

First-party clients for the internal JSON API (`/api/v1`). See [docs/API.md](../docs/API.md) and [CONTRACT.md](./CONTRACT.md).

| Path | Language | Purpose |
|------|----------|---------|
| [mock-api/](./mock-api/) | Python | Shared deterministic mock server for tests |
| [python/](./python/) | Python | HTTP client + FastMCP server |
| [kotlin/](./kotlin/) | Kotlin | Android-compatible HTTP client |

These packages are **separate** from the FastAPI app under `src/qr_chores/`. They must not import app code.
