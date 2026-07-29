"""Unit & integration tests for email notification service."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from qr_chores.config import Settings
from qr_chores.models.chore import Chore, ChoreCompletion, TimingStatus
from qr_chores.models.user import User, UserRole
from qr_chores.services.email import (
    clear_outbox,
    get_outbox,
    send_completion_note_email,
    send_email,
)
from qr_chores.services.timeutil import local_now, local_today


@pytest.fixture(autouse=True)
def reset_email_outbox():
    clear_outbox()
    yield
    clear_outbox()


@pytest.mark.asyncio
async def test_send_completion_note_email_parent_id(
    db_session: AsyncSession, test_settings: Settings
):
    parent = User(
        email="parent1@example.com",
        first_name="Dad",
        last_name="Doe",
        display_name="Dad Doe",
        password_hash="hash",
        role=UserRole.parent,
        is_active=True,
    )
    db_session.add(parent)
    await db_session.flush()

    child = User(
        email="child1@example.com",
        first_name="Kid",
        last_name="Doe",
        display_name="Kid Doe",
        password_hash="hash",
        role=UserRole.child,
        parent_id=parent.id,
        is_active=True,
    )
    db_session.add(child)
    await db_session.flush()

    chore = Chore(
        title="Feed Cat",
        qr_token="qr-cat-123",
        due_time=local_now(test_settings).time(),
        base_points=10,
        assignee_user_id=child.id,
    )
    db_session.add(chore)
    await db_session.flush()

    completion = ChoreCompletion(
        chore_id=chore.id,
        user_id=child.id,
        local_date=local_today(test_settings),
        completed_at=local_now(test_settings),
        timing=TimingStatus.on_time,
        notes="We are out of cat food!",
        points_awarded=10,
    )
    db_session.add(completion)
    await db_session.commit()

    await send_completion_note_email(
        db=db_session,
        settings=test_settings,
        completion=completion,
        chore=chore,
        child=child,
        notes="We are out of cat food!",
    )

    outbox = get_outbox()
    assert len(outbox) == 1
    item = outbox[0]
    assert item["to"] == ["parent1@example.com"]
    assert "[QR Chores] Note from Kid Doe on Feed Cat" in item["subject"]
    assert "We are out of cat food!" in item["body"]


@pytest.mark.asyncio
async def test_send_completion_note_email_empty_note(
    db_session: AsyncSession, test_settings: Settings
):
    child = User(
        email="child2@example.com",
        first_name="Kid",
        last_name="Two",
        display_name="Kid Two",
        password_hash="hash",
        role=UserRole.child,
    )
    chore = Chore(
        title="Clean Room",
        qr_token="qr-clean-456",
        due_time=local_now(test_settings).time(),
    )
    completion = ChoreCompletion(
        chore_id=1,
        user_id=1,
        local_date=local_today(test_settings),
        completed_at=local_now(test_settings),
        timing=TimingStatus.on_time,
        points_awarded=5,
    )

    await send_completion_note_email(
        db=db_session,
        settings=test_settings,
        completion=completion,
        chore=chore,
        child=child,
        notes="   ",
    )
    assert len(get_outbox()) == 0


@pytest.mark.asyncio
async def test_send_completion_note_email_fallback_parents(
    db_session: AsyncSession, test_settings: Settings
):
    parent = User(
        email="fallback_parent@example.com",
        first_name="Mom",
        last_name="Smith",
        display_name="Mom Smith",
        password_hash="hash",
        role=UserRole.parent,
        is_active=True,
    )
    db_session.add(parent)
    await db_session.flush()

    child = User(
        email="child_noparent@example.com",
        first_name="Orphan",
        last_name="Smith",
        display_name="Orphan Smith",
        password_hash="hash",
        role=UserRole.child,
        parent_id=None,
        is_active=True,
    )
    db_session.add(child)
    await db_session.flush()

    chore = Chore(
        title="Water Plants",
        qr_token="qr-plants-789",
        due_time=local_now(test_settings).time(),
    )
    db_session.add(chore)
    await db_session.flush()

    completion = ChoreCompletion(
        chore_id=chore.id,
        user_id=child.id,
        local_date=local_today(test_settings),
        completed_at=local_now(test_settings),
        timing=TimingStatus.on_time,
        notes="Plants look dry.",
        points_awarded=10,
    )
    db_session.add(completion)
    await db_session.commit()

    await send_completion_note_email(
        db=db_session,
        settings=test_settings,
        completion=completion,
        chore=chore,
        child=child,
        notes="Plants look dry.",
    )

    outbox = get_outbox()
    assert len(outbox) == 1
    assert "fallback_parent@example.com" in outbox[0]["to"]


@pytest.mark.asyncio
async def test_send_email_with_smtp_host():
    smtp_settings = Settings(
        smtp_host="smtp.fake.com",
        smtp_port=587,
        smtp_user="user",
        smtp_password="password",
        smtp_from_email="noreply@test.com",
        smtp_use_tls=True,
    )

    mock_smtp = MagicMock()
    with patch("smtplib.SMTP", return_value=mock_smtp) as mock_smtp_cls:
        mock_smtp_cm = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp_cm

        await send_email(
            settings=smtp_settings,
            to_addresses=["parent@test.com"],
            subject="Test Subject",
            body="Test Body",
        )

        mock_smtp_cm.starttls.assert_called_once()
        mock_smtp_cm.login.assert_called_once_with("user", "password")
        mock_smtp_cm.send_message.assert_called_once()

    outbox = get_outbox()
    assert len(outbox) == 1
    assert outbox[0]["subject"] == "Test Subject"
