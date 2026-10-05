"""User registration and parent/child relationship helpers."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.passwords import hash_password
from qr_chores.models.user import ChildParentLink, User, UserRole, format_display_name


class UserServiceError(Exception):
    def __init__(self, message: str, code: str = "error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def normalize_username(email: str) -> str:
    """Normalize login username. No email-format validation."""
    value = (email or "").strip().lower()
    if not value:
        raise UserServiceError("Username is required.", "username_required")
    if len(value) > 320:
        raise UserServiceError("Username is too long.", "username_too_long")
    return value


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    username = normalize_username(email)
    result = await db.execute(select(User).where(User.email == username))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    role: UserRole,
    parent_id: int | None = None,
    is_active: bool = True,
) -> User:
    username = normalize_username(email)
    existing = await get_user_by_email(db, username)
    if existing is not None:
        raise UserServiceError("That username is already taken.", "username_taken")

    if not (password or "").strip():
        raise UserServiceError("Password is required.", "password_required")
    if len(password) > 256:
        raise UserServiceError("Password is too long.", "password_too_long")

    first = (first_name or "").strip()
    last = (last_name or "").strip()
    if not first:
        raise UserServiceError("First name is required.", "first_name_required")
    if not last:
        raise UserServiceError("Last name is required.", "last_name_required")

    if role == UserRole.child and parent_id is None:
        raise UserServiceError("Children must belong to a parent.", "parent_required")
    if role == UserRole.parent and parent_id is not None:
        raise UserServiceError("Parents cannot have a parent_id.", "invalid_parent")

    user = User(
        email=username,
        first_name=first,
        last_name=last,
        display_name=format_display_name(first, last),
        password_hash=hash_password(password),
        role=role,
        parent_id=parent_id,
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    return user


def child_managed_by(parent_id: int):
    """Children whose primary parent is ``parent_id``, plus extra parent links."""
    linked_ids = select(ChildParentLink.child_id).where(ChildParentLink.parent_id == parent_id)
    return or_(User.parent_id == parent_id, User.id.in_(linked_ids))


async def list_children_for_parent(
    db: AsyncSession,
    parent_id: int,
    *,
    include_inactive: bool = True,
) -> list[User]:
    q = (
        select(User)
        .where(User.role == UserRole.child, child_managed_by(parent_id))
        .order_by(User.first_name, User.last_name, User.id)
    )
    if not include_inactive:
        q = q.where(User.is_active.is_(True))
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_child_for_parent(
    db: AsyncSession,
    parent_id: int,
    child_id: int,
) -> User | None:
    result = await db.execute(
        select(User).where(
            User.id == child_id,
            User.role == UserRole.child,
            child_managed_by(parent_id),
        )
    )
    return result.scalar_one_or_none()


async def update_user_profile(
    db: AsyncSession,
    user: User,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    password: str | None = None,
    is_active: bool | None = None,
) -> User:
    if first_name is not None:
        first = first_name.strip()
        if not first:
            raise UserServiceError("First name is required.", "first_name_required")
        user.first_name = first
    if last_name is not None:
        last = last_name.strip()
        if not last:
            raise UserServiceError("Last name is required.", "last_name_required")
        user.last_name = last
    if email is not None:
        username = normalize_username(email)
        if username != user.email:
            clash = await get_user_by_email(db, username)
            if clash is not None and clash.id != user.id:
                raise UserServiceError("That username is already taken.", "username_taken")
            user.email = username
    if password is not None and password.strip():
        if len(password) > 256:
            raise UserServiceError("Password is too long.", "password_too_long")
        user.password_hash = hash_password(password)
    if is_active is not None:
        user.is_active = is_active
    user.sync_display_name()
    await db.flush()
    return user
