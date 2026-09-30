"""Unit tests for user registration helpers."""

from datetime import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.models.user import ChildParentLink, UserRole, format_display_name
from qr_chores.services.chores import list_all_chores
from qr_chores.services.qr import new_qr_token
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
async def test_second_parent_sees_and_manages_child(db_session: AsyncSession) -> None:
    primary = await create_user(
        db_session,
        email="mom-link@example.com",
        password="secret",
        first_name="Tawnia",
        last_name="Example",
        role=UserRole.parent,
    )
    second = await create_user(
        db_session,
        email="dad-link@example.com",
        password="secret",
        first_name="Andrew",
        last_name="Example",
        role=UserRole.parent,
    )
    child = await create_user(
        db_session,
        email="sam-link",
        password="kid-pass",
        first_name="Sam",
        last_name="Example",
        role=UserRole.child,
        parent_id=primary.id,
    )
    db_session.add(ChildParentLink(child_id=child.id, parent_id=second.id))
    await db_session.commit()

    assert child.parent_id == primary.id
    for parent in (primary, second):
        kids = await list_children_for_parent(db_session, parent.id)
        assert [k.id for k in kids] == [child.id]
        assert await get_child_for_parent(db_session, parent.id, child.id) is not None

    chore = Chore(
        title="Dishes",
        qr_token=new_qr_token(),
        due_time=time(18, 0),
        schedule_days="0123456",
        photo_policy=PhotoPolicy.none,
        base_points=5,
        assignee_user_id=child.id,
        is_active=True,
    )
    db_session.add(chore)
    await db_session.commit()
    for parent in (primary, second):
        chores = await list_all_chores(db_session, parent_id=parent.id)
        assert [c.id for c in chores] == [chore.id]


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


def test_normalize_username_too_long() -> None:
    with pytest.raises(UserServiceError) as exc:
        normalize_username("a" * 321)
    assert exc.value.code == "username_too_long"


@pytest.mark.asyncio
async def test_create_user_validation_errors(db_session: AsyncSession) -> None:
    parent = await create_user(
        db_session,
        email="p-val@example.com",
        password="secret",
        first_name="P",
        last_name="Val",
        role=UserRole.parent,
    )

    with pytest.raises(UserServiceError) as exc:
        await create_user(
            db_session,
            email="no-pass",
            password="   ",
            first_name="A",
            last_name="B",
            role=UserRole.parent,
        )
    assert exc.value.code == "password_required"

    with pytest.raises(UserServiceError) as exc:
        await create_user(
            db_session,
            email="long-pass",
            password="x" * 257,
            first_name="A",
            last_name="B",
            role=UserRole.parent,
        )
    assert exc.value.code == "password_too_long"

    with pytest.raises(UserServiceError) as exc:
        await create_user(
            db_session,
            email="no-first",
            password="ok",
            first_name="  ",
            last_name="B",
            role=UserRole.parent,
        )
    assert exc.value.code == "first_name_required"

    with pytest.raises(UserServiceError) as exc:
        await create_user(
            db_session,
            email="no-last",
            password="ok",
            first_name="A",
            last_name="",
            role=UserRole.parent,
        )
    assert exc.value.code == "last_name_required"

    with pytest.raises(UserServiceError) as exc:
        await create_user(
            db_session,
            email="parent-with-parent",
            password="ok",
            first_name="A",
            last_name="B",
            role=UserRole.parent,
            parent_id=parent.id,
        )
    assert exc.value.code == "invalid_parent"


@pytest.mark.asyncio
async def test_list_children_exclude_inactive(db_session: AsyncSession) -> None:
    parent = await create_user(
        db_session,
        email="list-p@example.com",
        password="secret",
        first_name="List",
        last_name="Parent",
        role=UserRole.parent,
    )
    active = await create_user(
        db_session,
        email="list-active",
        password="ok",
        first_name="Active",
        last_name="Kid",
        role=UserRole.child,
        parent_id=parent.id,
    )
    inactive = await create_user(
        db_session,
        email="list-inactive",
        password="ok",
        first_name="Inactive",
        last_name="Kid",
        role=UserRole.child,
        parent_id=parent.id,
        is_active=False,
    )
    all_kids = await list_children_for_parent(db_session, parent.id, include_inactive=True)
    only_active = await list_children_for_parent(db_session, parent.id, include_inactive=False)
    assert {k.id for k in all_kids} == {active.id, inactive.id}
    assert [k.id for k in only_active] == [active.id]


@pytest.mark.asyncio
async def test_update_profile_validation(db_session: AsyncSession) -> None:
    a = await create_user(
        db_session,
        email="upd-a",
        password="pass",
        first_name="A",
        last_name="One",
        role=UserRole.parent,
    )
    b = await create_user(
        db_session,
        email="upd-b",
        password="pass",
        first_name="B",
        last_name="Two",
        role=UserRole.parent,
    )

    with pytest.raises(UserServiceError) as exc:
        await update_user_profile(db_session, a, first_name="  ")
    assert exc.value.code == "first_name_required"

    with pytest.raises(UserServiceError) as exc:
        await update_user_profile(db_session, a, last_name="")
    assert exc.value.code == "last_name_required"

    with pytest.raises(UserServiceError) as exc:
        await update_user_profile(db_session, a, email=b.email)
    assert exc.value.code == "username_taken"

    with pytest.raises(UserServiceError) as exc:
        await update_user_profile(db_session, a, password="p" * 257)
    assert exc.value.code == "password_too_long"

    # same email is fine; empty password ignored; is_active toggle
    await update_user_profile(
        db_session,
        a,
        email=a.email,
        password="   ",
        is_active=False,
    )
    assert a.is_active is False
    await update_user_profile(db_session, a, is_active=True)
    assert a.is_active is True
