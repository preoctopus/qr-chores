"""E2E Playwright tests for Parent History Log and Proof Photo Viewing."""

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
def test_parent_history_page_and_filters(page: Page, base_url: str) -> None:
    """Verify history log viewing and filtering controls."""
    login_as_parent(page, base_url)

    # Navigate to History
    page.click('nav[aria-label="Parent"] a[href="/history"]')
    expect(page).to_have_url(f"{base_url}/history")
    expect(page.locator("h1")).to_contain_text("Completion history")

    # Verify filter controls are visible
    expect(page.locator('select[name="child_id"]')).to_be_visible()
    expect(page.locator('select[name="timing"]')).to_be_visible()
    expect(page.locator('button[type="submit"]', has_text="Filter")).to_be_visible()
