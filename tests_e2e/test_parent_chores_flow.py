"""E2E Playwright tests for Parent Chores Management (CRUD, QR, Print, Delete)."""

import re

import pytest
from playwright.sync_api import Page, expect


def login_as_parent(page: Page, base_url: str) -> None:
    """Helper to authenticate as parent user."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="email"]', "parent@example.com")
    page.fill('input[name="password"]', "ParentPassword123!")
    page.click('form[action="/login"] button')
    expect(page).to_have_url(f"{base_url}/today")


def create_chore_via_ui(
    page: Page,
    base_url: str,
    title: str = "Clean Room",
    points: str = "15",
) -> None:
    """Helper to create a chore using parent UI."""
    page.goto(f"{base_url}/chores/new")
    page.fill('input[name="title"]', title)
    page.fill('textarea[name="description"]', "Put toys in closet")
    page.select_option('select[name="assignee_user_id"]', index=1)
    page.fill('input[name="due_time"]', "18:00")
    page.fill('input[name="base_points"]', points)
    page.select_option('select[name="photo_policy"]', value="optional")
    page.click('button:has-text("Create chore")')
    expect(page).to_have_url(re.compile(r".*/chores/\d+/qr"))
    expect(page.locator("h1")).to_contain_text(title)


@pytest.mark.e2e
def test_create_and_view_chore(page: Page, base_url: str) -> None:
    """Verify creating a new chore for an assigned child."""
    login_as_parent(page, base_url)
    create_chore_via_ui(page, base_url, title="Clean Room", points="15")

    page.goto(f"{base_url}/chores")
    card = page.locator(".chore-card", has_text="Clean Room")
    expect(card).to_be_visible()
    expect(card).to_contain_text("Child User")
    expect(card).to_contain_text("15 pts")


@pytest.mark.e2e
def test_edit_chore(page: Page, base_url: str) -> None:
    """Verify editing an existing chore."""
    login_as_parent(page, base_url)
    create_chore_via_ui(page, base_url, title="Clean Room", points="15")

    page.goto(f"{base_url}/chores")
    card = page.locator(".chore-card", has_text="Clean Room")
    card.locator('a[href*="/edit"]').click()

    page.fill('input[name="title"]', "Super Clean Room")
    page.fill('input[name="base_points"]', "25")
    page.click('button:has-text("Save changes")')

    expect(page).to_have_url(f"{base_url}/chores")
    updated_card = page.locator(".chore-card", has_text="Super Clean Room")
    expect(updated_card).to_be_visible()
    expect(updated_card).to_contain_text("25 pts")


@pytest.mark.e2e
def test_deactivate_and_reactivate_chore(page: Page, base_url: str) -> None:
    """Verify toggling active status of a chore."""
    login_as_parent(page, base_url)
    create_chore_via_ui(page, base_url, title="Active Chore", points="10")

    page.goto(f"{base_url}/chores")
    card = page.locator(".chore-card", has_text="Active Chore")

    # Deactivate
    card.locator('form[action*="/deactivate"] button').click()
    expect(page).to_have_url(f"{base_url}/chores")

    inactive_card = page.locator(".chore-card", has_text="Active Chore")
    expect(inactive_card.locator('form[action*="/activate"] button')).to_be_visible()

    # Reactivate
    inactive_card.locator('form[action*="/activate"] button').click()
    expect(page).to_have_url(f"{base_url}/chores")

    active_card = page.locator(".chore-card", has_text="Active Chore")
    expect(active_card.locator('form[action*="/deactivate"] button')).to_be_visible()


@pytest.mark.e2e
def test_view_chore_qr_and_print_sheet(page: Page, base_url: str) -> None:
    """Verify QR code page and sticker print sheet view."""
    login_as_parent(page, base_url)
    create_chore_via_ui(page, base_url, title="QR Test Chore", points="10")

    # Already on QR page after creation, check title and image
    expect(page.locator("h1")).to_contain_text("QR Test Chore")
    expect(page.locator('img[src*="/qr.png"]')).to_be_visible()

    # Navigate to print sheet
    page.goto(f"{base_url}/print/qrs")
    expect(page.locator(".print-sheet-header h1")).to_contain_text("QR Chores")
    expect(page.locator(".print-grid")).to_be_visible()


@pytest.mark.e2e
def test_delete_chore(page: Page, base_url: str) -> None:
    """Verify deleting a chore through confirmation screen."""
    login_as_parent(page, base_url)
    create_chore_via_ui(page, base_url, title="Chore To Delete", points="5")

    page.goto(f"{base_url}/chores")
    card = page.locator(".chore-card", has_text="Chore To Delete")
    card.locator('a[href*="/delete"]').click()

    expect(page.locator("h1")).to_contain_text("Delete chore?")
    page.click('button:has-text("Delete permanently")')

    expect(page).to_have_url(f"{base_url}/chores")
    expect(page.locator(".chore-card", has_text="Chore To Delete")).not_to_be_visible()
