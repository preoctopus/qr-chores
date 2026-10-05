"""E2E Playwright tests for Parent Today Live Board."""

from datetime import time as time_type

import pytest
from playwright.sync_api import Page, expect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import qr_chores.db
from conftest import run_async
from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.services.qr import new_qr_token


def create_test_chore(assignee_id: int) -> str:
    """Create a chore in DB for E2E today board test and return its QR token."""

    async def _insert() -> str:
        token = new_qr_token()
        session_factory: async_sessionmaker[AsyncSession] = qr_chores.db.SessionLocal
        async with session_factory() as session:
            chore = Chore(
                title="Feed the Dog",
                description="Give food and fresh water",
                qr_token=token,
                due_time=time_type(23, 59),
                schedule_days="0123456",
                photo_policy=PhotoPolicy.optional,
                base_points=15,
                is_active=True,
                assignee_user_id=assignee_id,
            )
            session.add(chore)
            await session.commit()
            return token

    return run_async(_insert())


def login_as_parent(page: Page, base_url: str) -> None:
    """Helper to authenticate as parent user."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="email"]', "parent@example.com")
    page.fill('input[name="password"]', "ParentPassword123!")
    page.click('form[action="/login"] button')
    expect(page).to_have_url(f"{base_url}/today")


@pytest.mark.e2e
def test_parent_today_board(page: Page, base_url: str) -> None:
    """Verify live status board for scheduled family chores."""
    login_as_parent(page, base_url)

    # Insert chore assigned to child@example.com (id 2)
    create_test_chore(assignee_id=2)

    # Navigate to Today
    page.goto(f"{base_url}/today")
    expect(page.locator("h1")).to_contain_text("Today’s board")

    # Verify chore card and pending status chip render
    card = page.locator(".chore-card", has_text="Feed the Dog")
    expect(card).to_be_visible()
    expect(card.locator(".chip")).to_contain_text("Pending")
