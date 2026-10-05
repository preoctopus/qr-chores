"""Parent dashboard: per-child Today board and day-grouped history with missed chores."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.auth.passwords import hash_password
from qr_chores.config import Settings
from qr_chores.models.chore import Chore, ChoreCompletion, PhotoPolicy, TimingStatus
from qr_chores.models.user import User, UserRole
from qr_chores.services.dashboard import (
    HISTORY_DEFAULT_DAYS,
    HISTORY_MAX_DAYS,
    ChildNotManagedError,
    build_today_dashboard,
    get_history_days,
    history_window,
)
from qr_chores.services.qr import new_qr_token
from qr_chores.services.timeutil import day_label, format_clock, frozen_at

MONDAY = date(2026, 10, 5)
assert MONDAY.weekday() == 0
CREATED = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _user(email: str, role: UserRole, *, first: str, parent_id: int | None = None) -> User:
    return User(
        email=email,
        password_hash=hash_password("pw-secret"),
        first_name=first,
        last_name="Test",
        display_name=first,
        role=role,
        parent_id=parent_id,
        is_active=True,
    )


def _chore(title: str, assignee: User, *, due: time, days: str = "0123456", **kw) -> Chore:
    return Chore(
        title=title,
        qr_token=new_qr_token(),
        due_time=due,
        schedule_days=days,
        photo_policy=PhotoPolicy.none,
        base_points=10,
        assignee_user_id=assignee.id,
        is_active=kw.pop("is_active", True),
        created_at=kw.pop("created_at", CREATED),
    )


def _done(chore: Chore, child: User, day: date, *, at: time, timing: TimingStatus, pts: int = 10):
    return ChoreCompletion(
        chore_id=chore.id,
        user_id=child.id,
        local_date=day,
        completed_at=datetime.combine(day, at, tzinfo=UTC),
        timing=timing,
        points_awarded=pts,
    )


@pytest.fixture
async def family(db_session: AsyncSession):
    parent = _user("p@example.com", UserRole.parent, first="Pat")
    other_parent = _user("o@example.com", UserRole.parent, first="Other")
    db_session.add_all([parent, other_parent])
    await db_session.flush()
    ava = _user("ava@example.com", UserRole.child, first="Ava", parent_id=parent.id)
    max_ = _user("max@example.com", UserRole.child, first="Max", parent_id=parent.id)
    zed = _user("zed@example.com", UserRole.child, first="Zed", parent_id=parent.id)
    stranger = _user("s@example.com", UserRole.child, first="Stranger", parent_id=other_parent.id)
    db_session.add_all([ava, max_, zed, stranger])
    await db_session.flush()

    dishes = _chore("Dishes", ava, due=time(8, 0))
    dog = _chore("Feed dog", ava, due=time(7, 0))
    homework = _chore("Homework", max_, due=time(20, 0))
    weekend = _chore("Mow lawn", max_, due=time(9, 0), days="56")
    old_inactive = _chore("Retired", max_, due=time(9, 0), is_active=False)
    theirs = _chore("Not yours", stranger, due=time(9, 0))
    db_session.add_all([dishes, dog, homework, weekend, old_inactive, theirs])
    await db_session.flush()
    await db_session.commit()
    return {
        "parent": parent,
        "other_parent": other_parent,
        "ava": ava,
        "max": max_,
        "zed": zed,
        "stranger": stranger,
        "dishes": dishes,
        "dog": dog,
        "homework": homework,
        "weekend": weekend,
        "theirs": theirs,
    }


@pytest.mark.asyncio
async def test_today_dashboard_groups_and_summary(
    db_session: AsyncSession, test_settings: Settings, family
) -> None:
    f = family
    db_session.add(_done(f["dishes"], f["ava"], MONDAY, at=time(12, 40), timing=TimingStatus.late))
    await db_session.commit()

    # 10:00 local: dog (7:00) overdue, dishes done late, homework (20:00) pending.
    with frozen_at(datetime(2026, 10, 5, 10, 0)):
        dash = await build_today_dashboard(db_session, test_settings, parent_id=f["parent"].id)

    s = dash.summary
    assert (s.total, s.done, s.pending, s.overdue, s.done_late) == (3, 1, 1, 1, 1)
    assert s.percent == 33

    names = [g.name for g in dash.groups]
    assert names == ["Ava", "Max", "Zed"]  # Zed has no chores but is still listed
    ava, max_, zed = dash.groups
    assert [r.chore.title for r in ava.rows] == ["Feed dog", "Dishes"]  # overdue before done
    assert (ava.done, ava.total, ava.overdue, ava.percent) == (1, 2, 1, 50)
    assert (max_.done, max_.total) == (0, 1)
    assert zed.total == 0 and zed.percent == 0
    assert all(r.chore.title != "Not yours" for r in dash.board)


@pytest.mark.asyncio
async def test_today_dashboard_child_filter_and_isolation(
    db_session: AsyncSession, test_settings: Settings, family
) -> None:
    f = family
    with frozen_at(MONDAY):
        dash = await build_today_dashboard(
            db_session, test_settings, parent_id=f["parent"].id, child_id=f["max"].id
        )
        assert [g.name for g in dash.groups] == ["Max"]
        assert [r.chore.title for r in dash.board] == ["Homework"]

        with pytest.raises(ChildNotManagedError):
            await build_today_dashboard(
                db_session, test_settings, parent_id=f["parent"].id, child_id=f["stranger"].id
            )


@pytest.mark.asyncio
async def test_today_dashboard_skips_inactive_child_without_chores(
    db_session: AsyncSession, test_settings: Settings, family
) -> None:
    f = family
    f["zed"].is_active = False
    await db_session.commit()
    with frozen_at(MONDAY):
        dash = await build_today_dashboard(db_session, test_settings, parent_id=f["parent"].id)
    assert "Zed" not in [g.name for g in dash.groups]


@pytest.mark.asyncio
async def test_history_days_missed_and_open(
    db_session: AsyncSession, test_settings: Settings, family
) -> None:
    f = family
    sunday = MONDAY - timedelta(days=1)
    db_session.add_all(
        [
            _done(f["dishes"], f["ava"], sunday, at=time(13, 0), timing=TimingStatus.early, pts=12),
            _done(f["dog"], f["ava"], sunday, at=time(14, 0), timing=TimingStatus.on_time),
            _done(f["dishes"], f["ava"], MONDAY, at=time(13, 0), timing=TimingStatus.on_time),
            _done(f["theirs"], f["stranger"], sunday, at=time(13, 0), timing=TimingStatus.late),
        ]
    )
    await db_session.commit()

    with frozen_at(datetime(2026, 10, 5, 10, 0)):
        res = await get_history_days(db_session, test_settings, parent_id=f["parent"].id)

    assert res.end_date == MONDAY
    assert len(res.days) == HISTORY_DEFAULT_DAYS
    assert res.days[0].local_date == MONDAY  # newest first
    today, sun = res.days[0], res.days[1]

    # Today: dishes done; dog + homework open (not missed yet).
    assert (today.done, len(today.missed), today.open_count, today.scheduled) == (1, 0, 2, 3)

    # Sunday: two of Ava's done; Max missed homework + weekend lawn; stranger excluded.
    assert sun.done == 2 and sun.points == 22
    assert [c.title for c in sun.missed] == ["Mow lawn", "Homework"]  # by due time
    assert sun.scheduled == 4 and sun.percent == 50

    # Older days exist because chores were created on Sep 1.
    assert res.older_end == res.start_date - timedelta(days=1)
    assert res.newer_start is None


@pytest.mark.asyncio
async def test_history_days_respects_created_at_schedule_and_filters(
    db_session: AsyncSession, test_settings: Settings, family
) -> None:
    f = family
    tuesday_before = MONDAY - timedelta(days=6)
    f["homework"].created_at = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)  # Saturday
    db_session.add(
        _done(f["dog"], f["ava"], tuesday_before, at=time(13, 0), timing=TimingStatus.late)
    )
    await db_session.commit()

    with frozen_at(MONDAY):
        by_max = await get_history_days(
            db_session, test_settings, parent_id=f["parent"].id, child_id=f["max"].id
        )
        days = {d.local_date: d for d in by_max.days}
        # Homework missed only from its creation day (Sat) onward.
        assert [c.title for c in days[date(2026, 10, 3)].missed] == ["Mow lawn", "Homework"]
        assert [c.title for c in days[date(2026, 10, 2)].missed] == []  # Fri, before created
        assert all(c.title != "Retired" for d in by_max.days for c in d.missed)

        by_chore = await get_history_days(
            db_session, test_settings, parent_id=f["parent"].id, chore_id=f["dog"].id
        )
        assert {c.title for d in by_chore.days for c in d.missed} == {"Feed dog"}

        late_only = await get_history_days(
            db_session, test_settings, parent_id=f["parent"].id, timing="late"
        )
        assert sum(len(d.missed) for d in late_only.days) == 0
        assert sum(d.open_count for d in late_only.days) == 0
        assert [d.done for d in late_only.days if d.done] == [1]

        bogus_timing = await get_history_days(
            db_session, test_settings, parent_id=f["parent"].id, timing="nope"
        )
        assert sum(len(d.missed) for d in bogus_timing.days) > 0


@pytest.mark.asyncio
async def test_history_days_navigation(
    db_session: AsyncSession, test_settings: Settings, family
) -> None:
    f = family
    with frozen_at(MONDAY):
        res = await get_history_days(
            db_session,
            test_settings,
            parent_id=f["parent"].id,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 7),
        )
    assert (res.start_date, res.end_date) == (date(2026, 9, 1), date(2026, 9, 7))
    assert res.older_start is None  # nothing before Sep 1
    assert (res.newer_start, res.newer_end) == (date(2026, 9, 8), date(2026, 9, 14))


@pytest.mark.asyncio
async def test_history_days_no_data(db_session: AsyncSession, test_settings: Settings) -> None:
    lonely = _user("lonely@example.com", UserRole.parent, first="Lonely")
    db_session.add(lonely)
    await db_session.commit()
    with frozen_at(MONDAY):
        res = await get_history_days(db_session, test_settings, parent_id=lonely.id)
    assert all(d.is_empty and d.percent == 0 for d in res.days)
    assert res.older_start is None


def test_history_window_clamps() -> None:
    assert history_window(MONDAY, None, None) == (MONDAY - timedelta(days=13), MONDAY)
    assert history_window(MONDAY, None, MONDAY + timedelta(days=5))[1] == MONDAY
    assert history_window(MONDAY, MONDAY, MONDAY - timedelta(days=3)) == (
        MONDAY - timedelta(days=3),
        MONDAY - timedelta(days=3),
    )
    start, end = history_window(MONDAY, date(2025, 1, 1), MONDAY)
    assert (end - start).days + 1 == HISTORY_MAX_DAYS


def test_day_label_and_format_clock(test_settings: Settings) -> None:
    assert day_label(MONDAY, MONDAY) == "Today"
    assert day_label(MONDAY - timedelta(days=1), MONDAY) == "Yesterday"
    assert day_label(date(2026, 10, 1), MONDAY) == "Thu, Oct 1"
    assert day_label(date(2025, 12, 31), MONDAY) == "Wed, Dec 31, 2025"
    # 12:42 UTC → 7:42 AM in America/Chicago (CDT)
    assert format_clock(datetime(2026, 10, 5, 12, 42, tzinfo=UTC), test_settings) == "7:42 AM"
    # Naive values are local wall time (SQLite round-trip of local_now()).
    assert format_clock(datetime(2026, 10, 5, 7, 42), test_settings) == "7:42 AM"


# --- HTTP ---------------------------------------------------------------------------------


async def _seed_http(app, parent_user: User, child_user: User):
    async with app.state.session_factory() as session:
        chore_a = _chore("Unload dishwasher", child_user, due=time(7, 0))
        chore_b = _chore("Make bed", child_user, due=time(21, 0))
        session.add_all([chore_a, chore_b])
        await session.flush()
        session.add(
            _done(
                chore_a,
                child_user,
                MONDAY - timedelta(days=1),
                at=time(13, 0),
                timing=TimingStatus.on_time,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_today_and_history_html(
    app, client: AsyncClient, parent_user: User, child_user: User
) -> None:
    await _seed_http(app, parent_user, child_user)
    await client.post("/login", data={"email": parent_user.email, "password": "parent-pass"})

    with frozen_at(datetime(2026, 10, 5, 10, 0)):
        today = await client.get("/today")
        assert today.status_code == 200
        assert "of 2 done" in today.text
        assert "1 overdue" in today.text
        assert 'class="child-group"' in today.text
        assert "Daughter" in today.text

        history = await client.get("/history")
        assert history.status_code == 200
        assert "Yesterday" in history.text
        assert "chip-missed" in history.text  # Make bed missed yesterday
        assert "day-strip" in history.text
        assert "← Older" in history.text

        filtered = await client.get(f"/history?child_id={child_user.id}&timing=on_time")
        assert "chip-missed" not in filtered.text
        assert f"child_id={child_user.id}" in filtered.text  # carried into nav links

        bad_dates = await client.get("/history?start_date=nope&end_date=also-nope")
        assert bad_dates.status_code == 200


@pytest.mark.asyncio
async def test_today_and_history_days_api(
    app, client: AsyncClient, parent_user: User, child_user: User
) -> None:
    await _seed_http(app, parent_user, child_user)
    login = await client.post(
        "/api/v1/auth/login", json={"email": parent_user.email, "password": "parent-pass"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    with frozen_at(datetime(2026, 10, 5, 10, 0)):
        today = (await client.get("/api/v1/today", headers=headers)).json()
        assert today["summary"] == {
            "total": 2,
            "done": 0,
            "pending": 1,
            "overdue": 1,
            "done_late": 0,
            "points_today": 0,
        }
        assert today["children"][0]["child_id"] == child_user.id
        assert len(today["children"][0]["items"]) == 2
        assert len(today["board"]) == 2

        missing = await client.get("/api/v1/today?child_id=99999", headers=headers)
        assert missing.status_code == 404

        days = (await client.get("/api/v1/history/days", headers=headers)).json()
        assert days["end_date"] == "2026-10-05"
        yesterday = days["days"][1]
        assert yesterday["local_date"] == "2026-10-04"
        assert yesterday["done"] == 1 and yesterday["missed_count"] == 1
        assert yesterday["missed"][0]["chore_title"] == "Make bed"
        assert yesterday["completions"][0]["chore_title"] == "Unload dishwasher"
        assert days["days"][0]["open_count"] == 2

        windowed = await client.get(
            "/api/v1/history/days?start_date=2026-10-01&end_date=2026-10-02", headers=headers
        )
        assert [d["local_date"] for d in windowed.json()["days"]] == ["2026-10-02", "2026-10-01"]
