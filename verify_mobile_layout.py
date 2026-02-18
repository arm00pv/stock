from playwright.sync_api import sync_playwright

def verify_mobile_layout():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 375, "height": 667})

        try:
            page.goto("http://localhost:5000")
            page.wait_for_selector(".container")

            # Check Container Width
            container_width = page.evaluate("document.querySelector('.container').offsetWidth")
            viewport_width = page.evaluate("document.documentElement.clientWidth")

            print(f"Container Width: {container_width}, Viewport Width: {viewport_width}")

            if abs(container_width - viewport_width) > 1: # Allow 1px rounding
                print(f"[FAIL] Container is not full width. Diff: {abs(container_width - viewport_width)}")
            else:
                print("[PASS] Container matches viewport width.")

            # Re-check for horizontal overflow
            scroll_width = page.evaluate("document.documentElement.scrollWidth")
            if scroll_width > viewport_width:
                 print(f"[WARN] Body has horizontal scroll (Scroll: {scroll_width}).")
            else:
                 print("[PASS] No horizontal scroll.")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_mobile_layout()
