"""Seed parent and child accounts for local / first deploy."""

import asyncio
import sys

from sqlalchemy import select

from qr_chores.auth.passwords import hash_password
from qr_chores.config import get_settings
from qr_chores.db import SessionLocal, init_db
from qr_chores.models.user import User, UserRole, format_display_name
from qr_chores.services.achievements import ensure_default_achievements
from qr_chores.services.points import DEFAULT_BONUSES, set_setting

DEFAULT_USERS = (
    {
        "email": "dad@example.com",
        "first_name": "Dad",
        "last_name": "Example",
        "role": UserRole.parent,
        "password_key": "parent",
        "parent_email": None,
    },
    {
        "email": "mom@example.com",
        "first_name": "Mom",
        "last_name": "Example",
        "role": UserRole.parent,
        "password_key": "parent",
        "parent_email": None,
    },
    {
        "email": "daughter@example.com",
        "first_name": "Daughter",
        "last_name": "Example",
        "role": UserRole.child,
        "password_key": "child",
        "parent_email": "dad@example.com",
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
        by_email: dict[str, User] = {}
        for spec in DEFAULT_USERS:
            email = spec["email"]
            result = await db.execute(select(User).where(User.email == email))
            existing = result.scalar_one_or_none()
            if existing is not None:
                print(f"skip  {email} (exists)")
                by_email[email] = existing
                continue
            parent_id = None
            parent_email = spec.get("parent_email")
            if parent_email:
                parent = by_email.get(parent_email)
                if parent is None:
                    parent_row = await db.execute(select(User).where(User.email == parent_email))
                    parent = parent_row.scalar_one_or_none()
                parent_id = parent.id if parent is not None else None
            first = spec["first_name"]
            last = spec["last_name"]
            user = User(
                email=email,
                first_name=first,
                last_name=last,
                display_name=format_display_name(first, last),
                role=spec["role"],
                password_hash=hash_password(passwords[spec["password_key"]]),
                parent_id=parent_id,
                is_active=True,
            )
            db.add(user)
            await db.flush()
            by_email[email] = user
            created += 1
            print(f"create {email} ({spec['role'].value})")

        ach_created = await ensure_default_achievements(db)
        for key, value in DEFAULT_BONUSES.items():
            # only set defaults if missing
            from qr_chores.models.rewards import AppSetting

            existing_setting = await db.get(AppSetting, key)
            if existing_setting is None:
                await set_setting(db, key, value)

        await db.commit()
        print(f"done — {created} user(s) created, {ach_created} achievement(s) seeded")


def main() -> None:
    try:
        asyncio.run(seed())
    except Exception as exc:  # noqa: BLE001
        print(f"seed failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
