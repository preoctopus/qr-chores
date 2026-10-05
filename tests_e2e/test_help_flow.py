"""E2E Playwright tests for In-App User Guide (/help)."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_help_page_unauthenticated(page: Page, base_url: str) -> None:
    """Verify help guide renders for unauthenticated users."""
    page.goto(f"{base_url}/help")
    expect(page.locator("h1")).to_contain_text("Using QR Chores")
    expect(page.locator(".brand")).to_contain_text("QR Chores")


@pytest.mark.e2e
def test_help_page_authenticated_navigation(page: Page, base_url: str) -> None:
    """Verify navigating to help from topbar when authenticated as parent."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="email"]', "parent@example.com")
    page.fill('input[name="password"]', "ParentPassword123!")
    page.click('form[action="/login"] button')
    expect(page).to_have_url(f"{base_url}/today")

    # Click Help in topbar
    page.click('header .topbar-meta a[href="/help"]')
    expect(page).to_have_url(f"{base_url}/help")
    expect(page.locator("h1")).to_contain_text("Using QR Chores")
