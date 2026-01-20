from playwright.sync_api import sync_playwright

def verify_mobile_layout():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Mobile viewport (iPhone SE size)
        page = browser.new_page(viewport={"width": 375, "height": 667})

        try:
            page.goto("http://localhost:5000")
            page.wait_for_selector(".container")

            # Check for body horizontal overflow
            scroll_width = page.evaluate("document.documentElement.scrollWidth")
            client_width = page.evaluate("document.documentElement.clientWidth")

            print(f"Viewport Width: {client_width}, Scroll Width: {scroll_width}")

            if scroll_width > client_width:
                print("[FAIL] Body has horizontal scroll (Content truncated/overflowing).")
                # Identify wide elements
                wide_elements = page.evaluate("""() => {
                    const elements = document.querySelectorAll('*');
                    const wide = [];
                    const viewportWidth = document.documentElement.clientWidth;
                    elements.forEach(el => {
                        if (el.offsetWidth > viewportWidth) {
                            wide.push(el.tagName + '.' + el.className);
                        }
                    });
                    return wide;
                }""")
                print(f"Wide elements: {wide_elements}")
            else:
                print("[PASS] No global horizontal scroll detected.")

            # Check specific containers
            # Portfolio Table should be scrollable internally, not force body scroll
            page.click("button[onclick=\"openTab(event, 'PortfolioMain')\"]")
            table_container = page.locator(".table-responsive").first
            if table_container.is_visible():
                is_scrollable = page.evaluate("""(el) => {
                    return el.scrollWidth > el.clientWidth;
                }""", table_container.element_handle())
                print(f"Table container internal scrollable: {is_scrollable}")

            page.screenshot(path="example_pages/mobile_check.png")
            print("Saved mobile check screenshot.")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_mobile_layout()
