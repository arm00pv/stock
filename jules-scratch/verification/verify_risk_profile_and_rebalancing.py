import re
import time
from playwright.sync_api import sync_playwright, expect

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    # Wait for the server to start
    time.sleep(15)

    # Log in
    page.goto("http://127.0.0.1:8000/login")
    page.get_by_label("Username").fill("testuser")
    page.get_by_label("Password").fill("password")
    page.get_by_role("button", name="Login").click()

    # Wait for the main page to load
    expect(page).to_have_url("http://127.0.0.1:8000/")

    # Go to the settings tab
    page.get_by_role("button", name="Settings").click()

    # Change the risk profile for the main portfolio
    page.get_by_label("Main:").select_option("Aggressive")

    # Go to the main portfolio tab
    page.get_by_role("button", name="Main").first.click()

    # Click the rebalance button
    page.get_by_role("button", name="Rebalance").first.click()

    # Wait for the modal to appear
    expect(page.locator(".modal")).to_be_visible()

    # Take a screenshot of the rebalancing modal
    page.screenshot(path="jules-scratch/verification/rebalancing_modal.png")

    browser.close()

with sync_playwright() as playwright:
    run(playwright)