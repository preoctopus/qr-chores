"""E2E Playwright tests for Parent Children Management."""

import pytest
from playwright.sync_api import Page, expect


def login_as_parent(page: Page, base_url: str) -> None:
    """Helper to authenticate as parent user."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="email"]', "parent@example.com")
    page.fill('input[name="password"]', "ParentPassword123!")
    page.click('form[action="/login"] button')
    expect(page).to_have_url(f"{base_url}/today")


@pytest.mark.e2e
def test_add_new_child(page: Page, base_url: str) -> None:
    """Verify adding a new child account under parent management."""
    login_as_parent(page, base_url)

    # Navigate to Children list
    page.click('nav[aria-label="Parent"] a[href="/children"]')
    expect(page).to_have_url(f"{base_url}/children")

    # Click Add Child
    page.click('a[href="/children/new"]')
    expect(page).to_have_url(f"{base_url}/children/new")

    # Fill form
    page.fill('input[name="first_name"]', "Alex")
    page.fill('input[name="last_name"]', "Smith")
    page.fill('input[name="email"]', "alex@example.com")
    page.fill('input[name="password"]', "AlexPassword123!")
    page.click('button:has-text("Create child")')

    expect(page).to_have_url(f"{base_url}/children")
    card = page.locator(".chore-card", has_text="Alex Smith")
    expect(card).to_be_visible()
    expect(card).to_contain_text("alex@example.com")


@pytest.mark.e2e
def test_edit_child(page: Page, base_url: str) -> None:
    """Verify editing a child profile."""
    login_as_parent(page, base_url)

    # First add a child
    page.goto(f"{base_url}/children/new")
    page.fill('input[name="first_name"]', "Alex")
    page.fill('input[name="last_name"]', "Smith")
    page.fill('input[name="email"]', "alex@example.com")
    page.fill('input[name="password"]', "AlexPassword123!")
    page.click('button:has-text("Create child")')
    expect(page).to_have_url(f"{base_url}/children")

    card = page.locator(".chore-card", has_text="Alex Smith")
    card.locator('a[href*="/edit"]').click()

    page.fill('input[name="first_name"]', "Alexander")
    page.click('button:has-text("Save changes")')

    expect(page).to_have_url(f"{base_url}/children")
    updated_card = page.locator(".chore-card", has_text="Alexander Smith")
    expect(updated_card).to_be_visible()


@pytest.mark.e2e
def test_toggle_child_active_status(page: Page, base_url: str) -> None:
    """Verify deactivating and reactivating a child account."""
    login_as_parent(page, base_url)

    # First add a child
    page.goto(f"{base_url}/children/new")
    page.fill('input[name="first_name"]', "Alex")
    page.fill('input[name="last_name"]', "Smith")
    page.fill('input[name="email"]', "alex@example.com")
    page.fill('input[name="password"]', "AlexPassword123!")
    page.click('button:has-text("Create child")')
    expect(page).to_have_url(f"{base_url}/children")

    card = page.locator(".chore-card", has_text="Alex Smith")

    # Deactivate
    card.locator('form[action*="/deactivate"] button').click()
    expect(page).to_have_url(f"{base_url}/children")

    inactive_card = page.locator(".chore-card", has_text="Alex Smith")
    expect(inactive_card.locator('form[action*="/activate"] button')).to_contain_text("Activate")

    # Reactivate
    inactive_card.locator('form[action*="/activate"] button').click()
    expect(page).to_have_url(f"{base_url}/children")

    active_card = page.locator(".chore-card", has_text="Alex Smith")
    expect(active_card.locator('form[action*="/deactivate"] button')).to_contain_text("Deactivate")
