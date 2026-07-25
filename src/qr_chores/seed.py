"""Seed parent and child accounts for local / first deploy."""

import asyncio
import sys

from sqlalchemy import select

from qr_chores.auth.passwords import hash_password
from qr_chores.config import get_settings
from qr_chores.db import SessionLocal, init_db
from qr_chores.models.user import User, UserRole

DEFAULT_USERS = (
    {
        "email": "dad@example.com",
        "display_name": "Dad",
        "role": UserRole.parent,
        "password_key": "parent",
    },
    {
        "email": "mom@example.com",
        "display_name": "Mom",
        "role": UserRole.parent,
        "password_key": "parent",
    },
    {
        "email": "daughter@example.com",
        "display_name": "Daughter",
        "role": UserRole.child,
        "password_key": "child",
    },
)


async def seed() -> None:
    settings = get_settings()
    # Ensure parent dir exists for file-based SQLite URLs
    if settings.database_url.startswith("sqlite") and "///" in settings.database_url:
        from pathlib import Path

        # sqlite+aiosqlite:///./data/x.db or sqlite+aiosqlite:////abs/path
        raw = settings.database_url.split("///", 1)[-1]
        if raw and raw != ":memory:" and not raw.startswith(":memory:"):
            Path(raw).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    await init_db()

    passwords = {
        "parent": settings.seed_parent_password,
        "child": settings.seed_child_password,
    }

    async with SessionLocal() as db:
        created = 0
        for spec in DEFAULT_USERS:
            email = spec["email"]
            result = await db.execute(select(User).where(User.email == email))
            existing = result.scalar_one_or_none()
            if existing is not None:
                print(f"skip  {email} (exists)")
                continue
            user = User(
                email=email,
                display_name=spec["display_name"],
                role=spec["role"],
                password_hash=hash_password(passwords[spec["password_key"]]),
                is_active=True,
            )
            db.add(user)
            created += 1
            print(f"create {email} ({spec['role'].value})")
        await db.commit()
        print(f"done — {created} user(s) created")


def main() -> None:
    try:
        asyncio.run(seed())
    except Exception as exc:  # noqa: BLE001
        print(f"seed failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
