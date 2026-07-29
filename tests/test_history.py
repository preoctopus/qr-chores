"""Tests for completion history filtering, pagination, and summary stats (#20)."""

from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.passwords import hash_password
from qr_chores.config import Settings
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy, TimingStatus
from qr_chores.models.user import User, UserRole, format_display_name
from qr_chores.services.completion import get_parent_history
from qr_chores.services.timeutil import frozen_at


@pytest.mark.asyncio
async def test_get_parent_history_filters_and_stats(
    db_session: AsyncSession, test_settings: Settings
) -> None:
    # 1. Setup parent + 2 children + 2 chores
    parent = User(
        email="history_parent@example.com",
        password_hash=hash_password("secret123"),
        first_name="History",
        last_name="Parent",
        display_name=format_display_name("History", "Parent"),
        role=UserRole.parent,
        is_active=True,
    )
    db_session.add(parent)
    await db_session.flush()

    child1 = User(
        email="child1@example.com",
        password_hash=hash_password("secret123"),
        first_name="Child",
        last_name="One",
        display_name=format_display_name("Child", "One"),
        role=UserRole.child,
        parent_id=parent.id,
        is_active=True,
    )
    child2 = User(
        email="child2@example.com",
        password_hash=hash_password("secret123"),
        first_name="Child",
        last_name="Two",
        display_name=format_display_name("Child", "Two"),
        role=UserRole.child,
        parent_id=parent.id,
        is_active=True,
    )
    db_session.add_all([child1, child2])
    await db_session.flush()

    chore1 = Chore(
        title="Chore One",
        qr_token="token_one",
        due_time=time(18, 0),
        schedule_days="1,2,3,4,5,6,7",
        photo_policy=PhotoPolicy.none,
        base_points=10,
        assignee_user_id=child1.id,
        is_active=True,
    )
    chore2 = Chore(
        title="Chore Two",
        qr_token="token_two",
        due_time=time(18, 0),
        schedule_days="1,2,3,4,5,6,7",
        photo_policy=PhotoPolicy.none,
        base_points=20,
        assignee_user_id=child2.id,
        is_active=True,
    )
    db_session.add_all([chore1, chore2])
    await db_session.flush()

    # 2. Add completions across dates and timing
    today = date(2026, 7, 28)
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)

    with frozen_at(today):
        c1 = ChoreCompletion(
            chore_id=chore1.id,
            user_id=child1.id,
            local_date=today,
            completed_at=today,
            timing=TimingStatus.on_time,
            points_awarded=15,
        )
        c2 = ChoreCompletion(
            chore_id=chore2.id,
            user_id=child2.id,
            local_date=today,
            completed_at=today,
            timing=TimingStatus.late,
            points_awarded=18,
        )
        c3 = ChoreCompletion(
            chore_id=chore1.id,
            user_id=child1.id,
            local_date=yesterday,
            completed_at=yesterday,
            timing=TimingStatus.early,
            points_awarded=15,
        )
        c4 = ChoreCompletion(
            chore_id=chore1.id,
            user_id=child1.id,
            local_date=two_days_ago,
            completed_at=two_days_ago,
            timing=TimingStatus.on_time,
            points_awarded=15,
        )
        db_session.add_all([c1, c2, c3, c4])
        await db_session.commit()

        # 3. Test unfiltered history & stats
        res = await get_parent_history(db_session, test_settings, parent_id=parent.id)
        assert res.pagination.total_count == 4
        assert res.stats.total_completions == 4
        assert res.stats.completions_this_week == 4
        assert res.stats.on_time_count == 3  # c1, c3, c4 are on_time or early
        assert res.stats.on_time_rate == 75.0
        assert res.stats.total_points == 63
        assert res.stats.current_streak == 3  # today, yesterday, two_days_ago

        # 4. Filter by child1
        res_child1 = await get_parent_history(
            db_session, test_settings, parent_id=parent.id, child_id=child1.id
        )
        assert res_child1.pagination.total_count == 3
        assert all(c.user_id == child1.id for c in res_child1.completions)

        # 5. Filter by timing=late
        res_late = await get_parent_history(
            db_session, test_settings, parent_id=parent.id, timing="late"
        )
        assert res_late.pagination.total_count == 1
        assert res_late.completions[0].user_id == child2.id

        # 6. Filter by start_date and end_date
        res_range = await get_parent_history(
            db_session,
            test_settings,
            parent_id=parent.id,
            start_date=yesterday,
            end_date=today,
        )
        assert res_range.pagination.total_count == 3

        # 7. Pagination limit and page navigation
        res_page1 = await get_parent_history(
            db_session, test_settings, parent_id=parent.id, limit=2, page=1
        )
        assert len(res_page1.completions) == 2
        assert res_page1.pagination.total_pages == 2
        assert res_page1.pagination.has_next is True
        assert res_page1.pagination.has_prev is False

        res_page2 = await get_parent_history(
            db_session, test_settings, parent_id=parent.id, limit=2, page=2
        )
        assert len(res_page2.completions) == 2
        assert res_page2.pagination.has_next is False
        assert res_page2.pagination.has_prev is True


@pytest.mark.asyncio
async def test_parent_history_html_and_api_endpoints(
    client: AsyncClient, parent_user: User
) -> None:
    # 1. Login as parent_user
    login_resp = await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass"},
    )
    assert login_resp.status_code == 303

    # 2. GET /history HTML endpoint with query params
    html_resp = await client.get("/history?timing=on_time&page=1&limit=20")
    assert html_resp.status_code == 200
    assert "Completion history" in html_resp.text
    assert "On Time" in html_resp.text

    # 3. GET /api/v1/history JSON endpoint
    api_resp = await client.get("/api/v1/history?timing=on_time&page=1&limit=20")
    assert api_resp.status_code == 200
    body = api_resp.json()
    assert "items" in body
    assert "stats" in body
    assert "pagination" in body
    assert body["pagination"]["page"] == 1
