"""E2E Playwright tests for Child QR Chore Scanning, Photo Upload, & Celebration."""

from datetime import time as time_type
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import qr_chores.db
from conftest import run_async
from qr_chores.models.chore import Chore, PhotoPolicy
from qr_chores.services.qr import new_qr_token


def create_test_chore(assignee_id: int) -> str:
    """Create a chore in DB for E2E completion test and return its QR token."""

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


def create_dummy_jpeg(tmp_path: Path) -> Path:
    """Create a valid 1x1 pixel JPEG file for upload testing."""
    img_path = tmp_path / "proof.jpg"
    jpeg_bytes = bytes.fromhex(
        "ffd8ffe000104a46494600010101004000400000ffdb004300080606070605080707070909"
        "080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c"
        "30313434341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f000001"
        "0501010101010100000000000000000102030405060708090a0bffda0008010100003f00"
        "d2cf207f"
    )
    img_path.write_bytes(jpeg_bytes)
    return img_path


def login_as_child(page: Page, base_url: str) -> None:
    """Helper to authenticate as child user."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="email"]', "child@example.com")
    page.fill('input[name="password"]', "ChildPassword123!")
    page.click('form[action="/login"] button')
    expect(page).to_have_url(f"{base_url}/home")


@pytest.mark.e2e
def test_child_completes_chore_flow(
    page: Page, base_url: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Verify child navigating to QR URL, uploading photo & notes, and celebration UI."""
    login_as_child(page, base_url)

    # Insert test chore assigned to child@example.com (id 2)
    token = create_test_chore(assignee_id=2)

    # Navigate to QR token confirm route
    page.goto(f"{base_url}/c/{token}")

    # Verify confirmation page
    expect(page.locator("h1")).to_contain_text("Feed the Dog")
    expect(page.locator(".muted", has_text="Give food and fresh water")).to_be_visible()

    # Upload proof photo
    tmp_dir = tmp_path_factory.mktemp("proof_photos")
    photo_file = create_dummy_jpeg(tmp_dir)
    page.set_input_files('input[name="photo"]', str(photo_file))

    # Add notes
    page.fill('textarea[name="notes"]', "Dog was super hungry!")

    # Submit completion form
    page.click('button:has-text("I did it")')

    # Celebration UI check
    expect(page).to_have_url(f"{base_url}/c/{token}")
    expect(page.locator(".celebration-wrap")).to_be_visible()
    expect(page.locator("#points-pop")).to_contain_text("+20")
    expect(page.locator("#btn-replay-sound")).to_be_visible()
    expect(page.locator("#confetti")).to_be_attached()

    # Verify photo thumbnail link renders
    expect(page.locator('a[href*="/photos/"] img')).to_be_visible()

    # Re-visiting QR URL on same day displays already done state
    page.goto(f"{base_url}/c/{token}")
    expect(page.locator(".stat-label")).to_contain_text("Already done")
    expect(page.locator(".muted", has_text="Dog was super hungry!")).to_be_visible()
