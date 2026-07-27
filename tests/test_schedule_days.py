"""Schedule-days + frozen clock: weekdays-only chores, board, timing."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from qr_chores.config import Settings
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy, TimingStatus
from qr_chores.models.user import User
from qr_chores.services.chores import today_board
from qr_chores.services.completion import CompletionError, complete_chore
from qr_chores.services.points import points_balance, set_setting
from qr_chores.services.qr import new_qr_token
from qr_chores.services.timeutil import (
    clear_frozen_time,
    frozen_at,
    is_scheduled_on,
    local_now,
    local_today,
)

# Fixed reference dates (APP_TIMEZONE America/Chicago)
MONDAY = date(2026, 7, 27)  # weekday() == 0
SATURDAY = date(2026, 8, 1)  # weekday() == 5
SUNDAY = date(2026, 8, 2)  # weekday() == 6
WEEKDAYS = "01234"
WEEKENDS = "56"
TZ = "America/Chicago"


def test_reference_weekdays() -> None:
    assert MONDAY.weekday() == 0
    assert SATURDAY.weekday() == 5
    assert SUNDAY.weekday() == 6
    assert is_scheduled_on(WEEKDAYS, MONDAY)
    assert not is_scheduled_on(WEEKDAYS, SATURDAY)
    assert not is_scheduled_on(WEEKDAYS, SUNDAY)
    assert is_scheduled_on(WEEKENDS, SATURDAY)
    assert not is_scheduled_on(WEEKENDS, MONDAY)


def test_frozen_at_pins_local_today_and_now() -> None:
    settings = Settings(app_timezone=TZ)
    with frozen_at(SATURDAY, tz=TZ) as pinned:
        assert local_today(settings) == SATURDAY
        assert local_now(settings).date() == SATURDAY
        assert local_now(settings).hour == 12  # date freezes at noon
        assert pinned.tzinfo is not None

    # Restored after context — not still pinned to Saturday noon
    clear_frozen_time()
    with frozen_at(MONDAY, tz=TZ):
        assert local_today(settings) == MONDAY


def test_frozen_at_naive_datetime_is_local_wall_clock() -> None:
    settings = Settings(app_timezone=TZ)
    with frozen_at(datetime(2026, 7, 27, 20, 30), tz=TZ):
        now = local_now(settings)
        assert now.date() == MONDAY
        assert now.hour == 20
        assert now.minute == 30
        assert now.tzinfo == ZoneInfo(TZ)


def test_frozen_at_nested_restores_outer() -> None:
    settings = Settings(app_timezone=TZ)
    with frozen_at(MONDAY, tz=TZ):
        assert local_today(settings) == MONDAY
        with frozen_at(SATURDAY, tz=TZ):
            assert local_today(settings) == SATURDAY
        assert local_today(settings) == MONDAY


@pytest.mark.asyncio
async def test_weekdays_chore_rejected_on_saturday_domain(app, child_user: User) -> None:
    from qr_chores.config import get_settings

    settings = get_settings()

    async with app.state.session_factory() as session:
        chore = Chore(
            title="School nights only",
            qr_token=new_qr_token(),
            due_time=time(20, 0),
            schedule_days=WEEKDAYS,
            photo_policy=PhotoPolicy.none,
            base_points=10,
            is_active=True,
        )
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        child = await session.get(User, child_user.id)
        assert child

        with frozen_at(SATURDAY, tz=settings.app_timezone):
            assert local_today(settings) == SATURDAY
            with pytest.raises(CompletionError) as exc:
                await complete_chore(session, chore=chore, user=child, settings=settings)
            assert exc.value.code == "not_scheduled"


@pytest.mark.asyncio
async def test_weekdays_chore_completes_on_monday_domain(app, child_user: User) -> None:
    from qr_chores.config import get_settings

    settings = get_settings()
    async with app.state.session_factory() as session:
        await set_setting(session, "early_bonus_points", "0")
        await set_setting(session, "on_time_bonus_points", "0")
        await set_setting(session, "late_bonus_points", "0")
        chore = Chore(
            title="Weekday homework",
            qr_token=new_qr_token(),
            due_time=time(20, 0),
            schedule_days=WEEKDAYS,
            photo_policy=PhotoPolicy.none,
            base_points=10,
            is_active=True,
        )
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        child = await session.get(User, child_user.id)
        assert child

        with frozen_at(datetime(2026, 7, 27, 19, 0), tz=settings.app_timezone):
            # Monday 7pm — on-time window for 8pm due
            result = await complete_chore(session, chore=chore, user=child, settings=settings)
            assert result.already_done is False
            assert result.completion.local_date == MONDAY
            assert result.completion.timing == TimingStatus.on_time
            assert await points_balance(session, child.id) == 10


@pytest.mark.asyncio
async def test_today_board_filters_unscheduled_days(app) -> None:
    from qr_chores.config import get_settings

    settings = get_settings()
    async with app.state.session_factory() as session:
        session.add_all(
            [
                Chore(
                    title="Weekday only",
                    qr_token=new_qr_token(),
                    due_time=time(18, 0),
                    schedule_days=WEEKDAYS,
                    photo_policy=PhotoPolicy.none,
                    base_points=5,
                    is_active=True,
                ),
                Chore(
                    title="Weekend only",
                    qr_token=new_qr_token(),
                    due_time=time(10, 0),
                    schedule_days=WEEKENDS,
                    photo_policy=PhotoPolicy.none,
                    base_points=5,
                    is_active=True,
                ),
                Chore(
                    title="Every day",
                    qr_token=new_qr_token(),
                    due_time=time(12, 0),
                    schedule_days="0123456",
                    photo_policy=PhotoPolicy.none,
                    base_points=5,
                    is_active=True,
                ),
            ]
        )
        await session.commit()

        with frozen_at(SATURDAY, tz=settings.app_timezone):
            board = await today_board(session, settings)
            titles = {row.chore.title for row in board}
            assert "Weekend only" in titles
            assert "Every day" in titles
            assert "Weekday only" not in titles

        with frozen_at(MONDAY, tz=settings.app_timezone):
            board = await today_board(session, settings)
            titles = {row.chore.title for row in board}
            assert "Weekday only" in titles
            assert "Every day" in titles
            assert "Weekend only" not in titles


@pytest.mark.asyncio
async def test_late_classification_with_frozen_clock(app, child_user: User) -> None:
    from qr_chores.config import get_settings

    settings = get_settings()
    async with app.state.session_factory() as session:
        await set_setting(session, "early_bonus_points", "0")
        await set_setting(session, "on_time_bonus_points", "0")
        await set_setting(session, "late_bonus_points", "3")
        chore = Chore(
            title="Due early evening",
            qr_token=new_qr_token(),
            due_time=time(18, 0),  # 6pm + 15m grace → late after 6:15
            schedule_days="0123456",
            photo_policy=PhotoPolicy.none,
            base_points=5,
            is_active=True,
        )
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        child = await session.get(User, child_user.id)
        assert child

        with frozen_at(datetime(2026, 7, 27, 19, 0), tz=settings.app_timezone):
            result = await complete_chore(session, chore=chore, user=child, settings=settings)
            assert result.completion.timing == TimingStatus.late
            assert result.points.timing_bonus == 3
            assert result.completion.points_awarded == 8
            assert await points_balance(session, child.id) == 8


@pytest.mark.asyncio
async def test_html_weekdays_chore_saturday_blocked_monday_ok(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    app,
    freeze_app_time,
) -> None:
    """Parent creates weekdays-only chore; child blocked Sat, succeeds Mon."""
    await client.post(
        "/login",
        data={"email": parent_user.email, "password": "parent-pass", "next": ""},
    )
    create = await client.post(
        "/chores",
        data={
            "title": "Weekday trash",
            "description": "",
            "due_time": "20:00",
            "base_points": "10",
            "photo_policy": "none",
            # Mon–Fri only
            "schedule_day": ["0", "1", "2", "3", "4"],
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    async with app.state.session_factory() as session:
        chore = (
            await session.execute(select(Chore).where(Chore.title == "Weekday trash"))
        ).scalar_one()
        token = chore.qr_token
        assert chore.schedule_days == WEEKDAYS

    await client.post(
        "/login",
        data={"email": child_user.email, "password": "child-pass", "next": ""},
    )

    with freeze_app_time(SATURDAY):
        # Parent today board should not list weekdays-only chore
        await client.post(
            "/login",
            data={"email": parent_user.email, "password": "parent-pass", "next": ""},
        )
        today_sat = await client.get("/today")
        assert today_sat.status_code == 200
        assert "Weekday trash" not in today_sat.text

        await client.post(
            "/login",
            data={"email": child_user.email, "password": "child-pass", "next": ""},
        )
        blocked = await client.post(f"/c/{token}")
        assert blocked.status_code == 400
        assert "not scheduled" in blocked.text.lower() or "Can’t complete" in blocked.text

    with freeze_app_time(datetime(2026, 7, 27, 19, 30)):
        await client.post(
            "/login",
            data={"email": parent_user.email, "password": "parent-pass", "next": ""},
        )
        today_mon = await client.get("/today")
        assert "Weekday trash" in today_mon.text

        await client.post(
            "/login",
            data={"email": child_user.email, "password": "child-pass", "next": ""},
        )
        done = await client.post(f"/c/{token}")
        assert done.status_code == 200
        assert "Weekday trash" in done.text

    async with app.state.session_factory() as session:
        completion = (await session.execute(select(ChoreCompletion))).scalar_one()
        assert completion.local_date == MONDAY
        assert await session.scalar(select(func.count()).select_from(ChoreCompletion)) == 1


@pytest.mark.asyncio
async def test_api_weekdays_schedule_confirm_and_complete(
    client: AsyncClient,
    parent_user: User,
    child_user: User,
    freeze_app_time,
) -> None:
    parent_login = await client.post(
        "/api/v1/auth/login",
        json={"email": parent_user.email, "password": "parent-pass"},
    )
    parent_h = {"Authorization": f"Bearer {parent_login.json()['access_token']}"}

    created = await client.post(
        "/api/v1/chores",
        headers=parent_h,
        json={
            "title": "API weekday chore",
            "due_time": "21:00:00",
            "schedule_days": WEEKDAYS,
            "photo_policy": "none",
            "base_points": 7,
        },
    )
    assert created.status_code == 201, created.text
    qr_token = created.json()["qr_token"]
    assert created.json()["schedule_days"] == WEEKDAYS

    child_login = await client.post(
        "/api/v1/auth/login",
        json={"email": child_user.email, "password": "child-pass"},
    )
    child_h = {"Authorization": f"Bearer {child_login.json()['access_token']}"}

    with freeze_app_time(SUNDAY):
        confirm = await client.get(f"/api/v1/c/{qr_token}", headers=child_h)
        assert confirm.status_code == 200
        assert confirm.json()["scheduled_today"] is False

        complete = await client.post(f"/api/v1/c/{qr_token}/complete", headers=child_h)
        assert complete.status_code == 400
        assert complete.json()["detail"]["code"] == "not_scheduled"

        today = await client.get("/api/v1/today", headers=parent_h)
        titles = [row["chore"]["title"] for row in today.json()["board"]]
        assert "API weekday chore" not in titles

    with freeze_app_time(datetime(2026, 7, 27, 20, 0)):
        confirm = await client.get(f"/api/v1/c/{qr_token}", headers=child_h)
        assert confirm.json()["scheduled_today"] is True

        complete = await client.post(f"/api/v1/c/{qr_token}/complete", headers=child_h)
        assert complete.status_code == 200, complete.text
        assert complete.json()["already_done"] is False
        assert complete.json()["points"]["base"] == 7
        assert complete.json()["completion"]["local_date"] == MONDAY.isoformat()

        today = await client.get("/api/v1/today", headers=parent_h)
        row = next(r for r in today.json()["board"] if r["chore"]["title"] == "API weekday chore")
        assert row["done"] is True


@pytest.mark.asyncio
async def test_double_complete_same_scheduled_day_with_freeze(app, child_user: User) -> None:
    """Frozen Monday: complete once, second attempt already_done; still only one row."""
    from qr_chores.config import get_settings

    settings = get_settings()
    async with app.state.session_factory() as session:
        await set_setting(session, "early_bonus_points", "0")
        await set_setting(session, "on_time_bonus_points", "0")
        await set_setting(session, "late_bonus_points", "0")
        chore = Chore(
            title="Once Monday",
            qr_token=new_qr_token(),
            due_time=time(22, 0),
            schedule_days=WEEKDAYS,
            photo_policy=PhotoPolicy.none,
            base_points=4,
            is_active=True,
        )
        session.add(chore)
        await session.commit()
        await session.refresh(chore)
        child = await session.get(User, child_user.id)
        assert child

        with frozen_at(MONDAY, tz=settings.app_timezone):
            first = await complete_chore(session, chore=chore, user=child, settings=settings)
            second = await complete_chore(session, chore=chore, user=child, settings=settings)
            assert first.already_done is False
            assert second.already_done is True
            assert await points_balance(session, child.id) == 4
            assert await session.scalar(select(func.count()).select_from(ChoreCompletion)) == 1
