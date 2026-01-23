from playwright.sync_api import sync_playwright

def verify_centering():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Desktop viewport - use tall height to ensure container fits
        viewport_height = 1200
        page = browser.new_page(viewport={"width": 1280, "height": viewport_height})

        try:
            page.goto("http://localhost:5000")
            page.wait_for_selector(".container")

            # Get dimensions
            container_rect = page.evaluate("document.querySelector('.container').getBoundingClientRect()")

            top_space = container_rect['top']
            bottom_space = viewport_height - container_rect['bottom']

            print(f"Viewport Height: {viewport_height}")
            print(f"Container Top: {top_space}, Bottom: {bottom_space}")

            # Allow some tolerance (e.g. 20px) because of flex rendering or subpixel
            if abs(top_space - bottom_space) < 50:
                print("[PASS] Container appears centered vertically.")
            else:
                print(f"[FAIL] Container is not centered. Top: {top_space}, Bottom: {bottom_space}")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_centering()
