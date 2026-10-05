"""E2E Playwright tests for Authentication and Role Redirection."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_login_page_renders(page: Page, base_url: str) -> None:
    """Verify login page displays initial branding and input fields."""
    page.goto(f"{base_url}/login")
    expect(page.locator("h1")).to_contain_text("Welcome back")
    expect(page.locator('input[name="email"]')).to_be_visible()
    expect(page.locator('input[name="password"]')).to_be_visible()
    expect(page.locator('button[type="submit"]')).to_contain_text("Log in")


@pytest.mark.e2e
def test_invalid_login_credentials(page: Page, base_url: str) -> None:
    """Verify invalid credentials show error alert and remain on login page."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="email"]', "wrong@example.com")
    page.fill('input[name="password"]', "BadPassword123")
    page.click('button[type="submit"]')

    expect(page.locator(".alert-error")).to_be_visible()
    expect(page.locator(".alert-error")).to_contain_text("Invalid email or password")
    expect(page).to_have_url(f"{base_url}/login")


@pytest.mark.e2e
def test_parent_login_logout_flow(page: Page, base_url: str) -> None:
    """Verify parent user authentication, navigation, and logout."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="email"]', "parent@example.com")
    page.fill('input[name="password"]', "ParentPassword123!")
    page.click('button[type="submit"]')

    # Parent is redirected to /today
    expect(page).to_have_url(f"{base_url}/today")
    expect(page.locator(".user-chip")).to_contain_text("Parent User")

    # Parent tab navigation bar is present
    nav = page.locator('nav[aria-label="Parent"]')
    expect(nav).to_be_visible()
    expect(nav.locator('a[href="/today"]')).to_be_visible()
    expect(nav.locator('a[href="/history"]')).to_be_visible()
    expect(nav.locator('a[href="/children"]')).to_be_visible()
    expect(nav.locator('a[href="/chores"]')).to_be_visible()
    expect(nav.locator('a[href="/rewards"]')).to_be_visible()

    # Log out
    page.click('form[action="/logout"] button')
    expect(page).to_have_url(f"{base_url}/login")


@pytest.mark.e2e
def test_child_login_flow(page: Page, base_url: str) -> None:
    """Verify child user login redirects to /home."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="email"]', "child@example.com")
    page.fill('input[name="password"]', "ChildPassword123!")
    page.click('button[type="submit"]')

    # Child is redirected to /home
    expect(page).to_have_url(f"{base_url}/home")
    expect(page.locator(".user-chip")).to_contain_text("Child User")


@pytest.mark.e2e
def test_login_next_parameter_redirect(page: Page, base_url: str) -> None:
    """Verify next parameter redirects user to target URL upon authentication."""
    page.goto(f"{base_url}/login?next=/help")
    page.fill('input[name="email"]', "parent@example.com")
    page.fill('input[name="password"]', "ParentPassword123!")
    page.click('button[type="submit"]')

    expect(page).to_have_url(f"{base_url}/help")
