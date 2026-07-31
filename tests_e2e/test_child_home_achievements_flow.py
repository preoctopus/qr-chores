"""E2E Playwright tests for Child Home Dashboard and Achievements Collection."""

import pytest
from playwright.sync_api import Page, expect


def login_as_child(page: Page, base_url: str) -> None:
    """Helper to authenticate as child user."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="email"]', "child@example.com")
    page.fill('input[name="password"]', "ChildPassword123!")
    page.click('form[action="/login"] button')
    expect(page).to_have_url(f"{base_url}/home")


@pytest.mark.e2e
def test_child_home_dashboard(page: Page, base_url: str) -> None:
    """Verify child home dashboard displays points balance and assigned chores."""
    login_as_child(page, base_url)

    expect(page.locator("h1")).to_contain_text("Hey, Child")
    expect(page.locator(".stat-value").first).to_be_visible()


@pytest.mark.e2e
def test_child_achievements_page(page: Page, base_url: str) -> None:
    """Verify child achievements collection page."""
    login_as_child(page, base_url)

    page.goto(f"{base_url}/me/achievements")
    expect(page).to_have_url(f"{base_url}/me/achievements")

    expect(page.locator("h1")).to_contain_text("Achievements")
    expect(page.locator(".muted", has_text="unlocked")).to_be_visible()
