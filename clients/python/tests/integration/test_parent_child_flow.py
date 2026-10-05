"""Integration tests against mock-api via ASGI transport."""

from __future__ import annotations

import pytest
from tests.conftest import (
    CHILD_EMAIL,
    CHILD_PASSWORD,
    PARENT_EMAIL,
    PARENT_PASSWORD,
)

from qr_chores_client import (
    AuthError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    QrChoresClient,
)
from qr_chores_client.models import (
    AchievementCreate,
    AchievementUpdate,
    ChoreCreate,
    ChoreUpdate,
)


@pytest.mark.integration
async def test_login_parent_and_child(asgi_client: QrChoresClient):
    parent = await asgi_client.login(PARENT_EMAIL, PARENT_PASSWORD)
    assert parent.access_token == "parent-token"
    assert parent.user.role == "parent"

    child_client = QrChoresClient(
        asgi_client.base_url,
        transport=asgi_client._client._transport,
    )
    try:
        child = await child_client.login(CHILD_EMAIL, CHILD_PASSWORD)
        assert child.access_token == "child-token"
        assert child.user.role == "child"
    finally:
        await child_client.aclose()


@pytest.mark.integration
async def test_bad_login(asgi_client: QrChoresClient):
    with pytest.raises(AuthError):
        await asgi_client.login("nope@example.com", "wrong")


@pytest.mark.integration
async def test_parent_flow(parent_client: QrChoresClient):
    me = await parent_client.get_me()
    assert me.role == "parent"

    today = await parent_client.get_today()
    assert today.local_date
    assert len(today.board) >= 2

    history = await parent_client.get_history(limit=20)
    assert history.limit == 20
    assert any(i.chore_id == 1 for i in history.items)

    assert today.summary is not None and today.summary.done == 1
    assert today.children[0].child_id == 2
    days = await parent_client.get_history_days()
    assert days.days[0].done == 1 and days.days[0].open_count == 1

    children = await parent_client.list_children()
    assert any(c.role == "child" for c in children.children)
    created_child = await parent_client.create_child(
        {
            "email": f"kid-{id(parent_client)}@example.com",
            "password": "child-pass",
            "first_name": "Integration",
            "last_name": "Kid",
        }
    )
    assert created_child.parent_id is not None
    got = await parent_client.get_child(created_child.id)
    assert got.id == created_child.id
    renamed = await parent_client.update_child(created_child.id, {"first_name": "Integ"})
    assert "Integ" in renamed.display_name
    assert (await parent_client.deactivate_child(created_child.id)).is_active is False
    assert (await parent_client.activate_child(created_child.id)).is_active is True

    chores = await parent_client.list_chores()
    assert len(chores.chores) >= 3

    active_only = await parent_client.list_chores(include_inactive=False)
    assert all(c.is_active for c in active_only.chores)

    created = await parent_client.create_chore(
        ChoreCreate(
            title="Take out trash",
            description="Bins to curb",
            due_time="19:00:00",
            schedule_days="01234",
            photo_policy="optional",
            base_points=8,
        )
    )
    assert created.id >= 4
    assert created.qr_token.startswith("qr-")
    assert created.is_active is True

    fetched = await parent_client.get_chore(created.id)
    assert fetched.title == "Take out trash"

    updated = await parent_client.update_chore(
        created.id,
        ChoreUpdate(title="Trash night", clear_description=True),
    )
    assert updated.title == "Trash night"
    assert updated.description is None

    qr = await parent_client.get_qr_info(created.id)
    assert qr.chore_id == created.id
    assert qr.qr_token == created.qr_token
    png = await parent_client.get_qr_png(created.id)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"

    deactivated = await parent_client.deactivate_chore(created.id)
    assert deactivated.is_active is False
    activated = await parent_client.activate_chore(created.id)
    assert activated.is_active is True

    rewards = await parent_client.get_rewards()
    assert rewards.bonuses.early_bonus_points == 5
    assert any(a.title == "Early bird" for a in rewards.achievements)

    bonuses = await parent_client.update_bonuses(
        early_bonus_points=6,
        on_time_bonus_points=3,
        late_bonus_points=0,
    )
    assert bonuses.on_time_bonus_points == 3

    ach = await parent_client.create_achievement(
        AchievementCreate(
            title="Photo pro",
            criteria_type="photo_completions",
            threshold=3,
            points_reward=15,
        )
    )
    assert ach.is_active is True
    ach2 = await parent_client.update_achievement(
        ach.id, AchievementUpdate(title="Photo pro+", points_reward=20)
    )
    assert ach2.title == "Photo pro+"
    assert ach2.points_reward == 20
    toggled = await parent_client.toggle_achievement(ach.id)
    assert toggled.is_active is False

    photo = await parent_client.get_photo(1)
    assert photo[:8] == b"\x89PNG\r\n\x1a\n"

    deleted = await parent_client.delete_chore(created.id)
    assert deleted.deleted is True
    with pytest.raises(NotFoundError):
        await parent_client.get_chore(created.id)

    await parent_client.logout()
    assert parent_client.access_token is None


@pytest.mark.integration
async def test_child_flow(child_client: QrChoresClient, tiny_png: bytes):
    me = await child_client.get_me()
    assert me.role == "child"
    assert me.points_balance == 42

    home = await child_client.get_home()
    assert home.total_count >= 2
    assert home.points_balance == 42

    # Chore 1 already done today in seed
    conf_done = await child_client.get_confirm("qr-active-1")
    assert conf_done.already_done is True
    already = await child_client.complete_chore("qr-active-1")
    assert already.already_done is True
    assert already.points.total == 0

    # Photo required without photo → domain error
    conf = await child_client.get_confirm("qr-photo-required")
    assert conf.already_done is False
    with pytest.raises(DomainError) as ei:
        await child_client.complete_chore("qr-photo-required")
    assert ei.value.code == "photo_required"

    # Complete with photo
    result = await child_client.complete_chore(
        "qr-photo-required",
        photo=tiny_png,
        photo_filename="bed.png",
        photo_content_type="image/png",
    )
    assert result.already_done is False
    assert result.completion.has_photo is True
    assert result.points.total > 0

    photo = await child_client.get_photo(result.completion.id)
    assert photo[:4] == b"\x89PNG"

    ach = await child_client.get_achievements()
    assert ach.points_balance >= 42
    assert any(a.title == "Early bird" for a in ach.achievements)

    # Parent routes forbidden
    with pytest.raises(ForbiddenError):
        await child_client.get_today()

    # Unknown QR
    with pytest.raises(NotFoundError):
        await child_client.get_confirm("no-such-token")


@pytest.mark.integration
async def test_role_enforcement_parent_on_child(parent_client: QrChoresClient):
    with pytest.raises(ForbiddenError):
        await parent_client.get_home()
    with pytest.raises(ForbiddenError):
        await parent_client.get_achievements()


@pytest.mark.integration
async def test_unauthenticated(asgi_client: QrChoresClient):
    with pytest.raises(AuthError):
        await asgi_client.get_me()


@pytest.mark.integration
async def test_photo_missing(parent_client: QrChoresClient):
    with pytest.raises(NotFoundError):
        await parent_client.get_photo(99999)


@pytest.mark.integration
async def test_complete_optional_with_photo(
    child_client: QrChoresClient, parent_client: QrChoresClient, tiny_png: bytes
):
    """Create fresh optional chore and complete with optional photo as child."""
    chore = await parent_client.create_chore(
        ChoreCreate(title="Feed pet", photo_policy="optional", base_points=4)
    )
    # child_client may share state with parent through mock app
    result = await child_client.complete_chore(chore.qr_token, photo=tiny_png)
    assert result.completion.has_photo is True
    assert result.points.base == 4
