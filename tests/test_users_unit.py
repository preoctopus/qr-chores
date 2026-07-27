"""Unit tests for user registration helpers."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.models.user import UserRole, format_display_name
from qr_chores.services.users import (
    UserServiceError,
    create_user,
    get_child_for_parent,
    list_children_for_parent,
    normalize_username,
    update_user_profile,
)


def test_format_display_name() -> None:
    assert format_display_name("Ada", "Lovelace") == "Ada Lovelace"
    assert format_display_name("  Sam ", "  ") == "Sam"
    assert format_display_name("", "") == "User"


def test_normalize_username() -> None:
    assert normalize_username("  Kid@Example.COM ") == "kid@example.com"
    with pytest.raises(UserServiceError) as exc:
        normalize_username("   ")
    assert exc.value.code == "username_required"


@pytest.mark.asyncio
async def test_create_parent_and_child(db_session: AsyncSession) -> None:
    parent = await create_user(
        db_session,
        email="ParentX@example.com",
        password="secret",
        first_name="Pat",
        last_name="Parent",
        role=UserRole.parent,
    )
    assert parent.email == "parentx@example.com"
    assert parent.display_name == "Pat Parent"
    assert parent.parent_id is None

    child = await create_user(
        db_session,
        email="kid1",
        password="kid-pass",
        first_name="Kid",
        last_name="One",
        role=UserRole.child,
        parent_id=parent.id,
    )
    assert child.parent_id == parent.id
    kids = await list_children_for_parent(db_session, parent.id)
    assert [k.id for k in kids] == [child.id]
    assert await get_child_for_parent(db_session, parent.id, child.id) is not None
    assert await get_child_for_parent(db_session, parent.id + 999, child.id) is None


@pytest.mark.asyncio
async def test_duplicate_username(db_session: AsyncSession) -> None:
    await create_user(
        db_session,
        email="dup@example.com",
        password="x",
        first_name="A",
        last_name="B",
        role=UserRole.parent,
    )
    with pytest.raises(UserServiceError) as exc:
        await create_user(
            db_session,
            email="dup@example.com",
            password="y",
            first_name="C",
            last_name="D",
            role=UserRole.parent,
        )
    assert exc.value.code == "username_taken"


@pytest.mark.asyncio
async def test_child_requires_parent(db_session: AsyncSession) -> None:
    with pytest.raises(UserServiceError) as exc:
        await create_user(
            db_session,
            email="orphan",
            password="x",
            first_name="O",
            last_name="R",
            role=UserRole.child,
        )
    assert exc.value.code == "parent_required"


@pytest.mark.asyncio
async def test_update_profile(db_session: AsyncSession) -> None:
    user = await create_user(
        db_session,
        email="old",
        password="pass",
        first_name="Old",
        last_name="Name",
        role=UserRole.parent,
    )
    await update_user_profile(
        db_session,
        user,
        first_name="New",
        last_name="Name",
        email="new-user",
        password="new-pass",
    )
    assert user.email == "new-user"
    assert user.display_name == "New Name"
