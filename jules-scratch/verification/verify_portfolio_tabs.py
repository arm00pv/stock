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

    # Verify that the portfolio tabs are present
    expect(page.get_by_role("button", name="Main")).to_be_visible()
    expect(page.get_by_role("button", name="Monthly Dividend").first).to_be_visible()
    expect(page.get_by_role("button", name="Daily Investment")).to_be_visible()
    expect(page.get_by_role("button", name="High Yield Investment")).to_be_visible()

    # Take a screenshot
    page.screenshot(path="jules-scratch/verification/verification.png")

    browser.close()

with sync_playwright() as playwright:
    run(playwright)