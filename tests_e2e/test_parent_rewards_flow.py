"""E2E Playwright tests for Parent Rewards and Achievements Management."""

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
def test_update_timing_bonuses(page: Page, base_url: str) -> None:
    """Verify updating early, on-time, and late timing bonus points."""
    login_as_parent(page, base_url)

    # Navigate to Rewards
    page.click('nav[aria-label="Parent"] a[href="/rewards"]')
    expect(page).to_have_url(f"{base_url}/rewards")

    # Fill bonus form
    page.fill('input[name="early_bonus_points"]', "5")
    page.fill('input[name="on_time_bonus_points"]', "2")
    page.fill('input[name="late_bonus_points"]', "-1")

    page.click('form[action="/rewards/bonuses"] button[type="submit"]')

    expect(page).to_have_url(f"{base_url}/rewards")
    expect(page.locator('input[name="early_bonus_points"]')).to_have_value("5")
    expect(page.locator('input[name="on_time_bonus_points"]')).to_have_value("2")
    expect(page.locator('input[name="late_bonus_points"]')).to_have_value("-1")


@pytest.mark.e2e
def test_create_and_edit_achievement(page: Page, base_url: str) -> None:
    """Verify creating and editing a custom achievement."""
    login_as_parent(page, base_url)
    page.goto(f"{base_url}/rewards")

    # Click Add Achievement
    page.click('a[href="/rewards/achievements/new"]')
    expect(page).to_have_url(f"{base_url}/rewards/achievements/new")

    # Fill achievement form
    page.fill('input[name="title"]', "Custom Unique Achievement")
    page.fill('textarea[name="description"]', "Finish 3 chores early")
    page.select_option('select[name="criteria_type"]', value="complete_early_count")
    page.fill('input[name="threshold"]', "3")
    page.fill('input[name="points_reward"]', "25")

    page.click('button:has-text("Save")')
    expect(page).to_have_url(f"{base_url}/rewards")

    card = page.locator(".chore-card", has_text="Custom Unique Achievement")
    expect(card).to_be_visible()
    expect(card).to_contain_text("+25 pts")

    # Edit achievement
    card.locator('a[href*="/edit"]').click()
    page.fill('input[name="title"]', "Super Custom Achievement")
    page.fill('input[name="points_reward"]', "50")
    page.click('button:has-text("Save")')

    expect(page).to_have_url(f"{base_url}/rewards")
    updated_card = page.locator(".chore-card", has_text="Super Custom Achievement")
    expect(updated_card).to_be_visible()
    expect(updated_card).to_contain_text("+50 pts")


@pytest.mark.e2e
def test_toggle_achievement_active_status(page: Page, base_url: str) -> None:
    """Verify enabling and disabling an achievement."""
    login_as_parent(page, base_url)
    page.goto(f"{base_url}/rewards/achievements/new")

    page.fill('input[name="title"]', "Super Custom Achievement")
    page.fill('textarea[name="description"]', "Finish 3 chores early")
    page.select_option('select[name="criteria_type"]', value="complete_early_count")
    page.fill('input[name="threshold"]', "3")
    page.fill('input[name="points_reward"]', "50")
    page.click('button:has-text("Save")')
    expect(page).to_have_url(f"{base_url}/rewards")

    card = page.locator(".chore-card", has_text="Super Custom Achievement")

    # Disable
    card.locator('form[action*="/toggle"] button').click()
    expect(page).to_have_url(f"{base_url}/rewards")

    disabled_card = page.locator(".chore-card", has_text="Super Custom Achievement")
    expect(disabled_card.locator('form[action*="/toggle"] button')).to_contain_text("Enable")

    # Enable
    disabled_card.locator('form[action*="/toggle"] button').click()
    expect(page).to_have_url(f"{base_url}/rewards")

    enabled_card = page.locator(".chore-card", has_text="Super Custom Achievement")
    expect(enabled_card.locator('form[action*="/toggle"] button')).to_contain_text("Disable")
