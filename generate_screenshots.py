from playwright.sync_api import sync_playwright
import os

def generate_screenshots():
    output_dir = "example_pages"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Set viewport to a desktop size for better screenshots
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        # 8. Mobile View (Separate Context)
        mobile_page = browser.new_page(viewport={"width": 375, "height": 667})

        try:
            print("Navigating to home...")
            page.goto("http://localhost:5000")
            page.wait_for_selector(".container")

            # 1. Dashboard / Hot Stocks (Default)
            # Wait for chart to load if possible, or just take snap
            page.wait_for_timeout(1000) # Wait for animations
            page.screenshot(path=f"{output_dir}/dashboard.png")
            print(f"Saved {output_dir}/dashboard.png")

            # 2. Beta Features
            print("Switching to Beta Features...")
            page.click("button[onclick=\"openTab(event, 'BetaFeatures')\"]")
            page.wait_for_timeout(500)
            page.screenshot(path=f"{output_dir}/beta_features.png")
            print(f"Saved {output_dir}/beta_features.png")

            # 3. Portfolio
            print("Switching to Portfolio...")
            page.click("button[onclick=\"openTab(event, 'PortfolioMain')\"]")
            page.wait_for_timeout(500)
            page.screenshot(path=f"{output_dir}/portfolio.png")
            print(f"Saved {output_dir}/portfolio.png")

            # 4. Dark Mode
            print("Toggling Dark Mode...")
            page.click("#theme-toggle")
            page.wait_for_timeout(500) # Wait for transition
            # Go back to dashboard for the dark mode shot
            page.click("button[onclick=\"openTab(event, 'HotStocks')\"]")
            page.wait_for_timeout(500)
            page.screenshot(path=f"{output_dir}/dark_mode.png")
            print(f"Saved {output_dir}/dark_mode.png")

            # Reset Dark Mode
            page.click("#theme-toggle")

            # 5. Penny Stocks Tab
            print("Switching to Penny Stocks...")
            page.click("button[onclick=\"openTab(event, 'PennyStocks')\"]")
            page.wait_for_timeout(500)
            page.screenshot(path=f"{output_dir}/penny_stocks.png")
            print(f"Saved {output_dir}/penny_stocks.png")

            # 6. Comparison Feature (Beta)
            print("Capturing Comparison...")
            page.click("button[onclick=\"openTab(event, 'BetaFeatures')\"]")
            page.fill("#comp-t1", "AAPL")
            page.fill("#comp-t2", "MSFT")
            page.click("button:has-text('Compare')")
            # Wait for result table
            page.wait_for_selector("#comparison-result table", timeout=10000)
            page.screenshot(path=f"{output_dir}/comparison_result.png")
            print(f"Saved {output_dir}/comparison_result.png")

            # 7. Chat Interaction
            print("Capturing Chat...")
            page.fill("#chat-input", "Analyze AAPL")
            page.click("button:has-text('Send')")
            # Wait for bot response
            page.wait_for_selector(".message.bot", timeout=5000)
            page.screenshot(path=f"{output_dir}/chat_interaction.png")
            print(f"Saved {output_dir}/chat_interaction.png")

            # Mobile
            print("Capturing Mobile Dashboard...")
            mobile_page.goto("http://localhost:5000")
            mobile_page.wait_for_selector(".container")
            mobile_page.wait_for_timeout(1000)
            mobile_page.screenshot(path=f"{output_dir}/mobile_dashboard.png")
            print(f"Saved {output_dir}/mobile_dashboard.png")

        except Exception as e:
            print(f"Error generating screenshots: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    generate_screenshots()
