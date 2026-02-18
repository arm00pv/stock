from playwright.sync_api import sync_playwright

def verify_mobile_layout():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 375, "height": 667})

        try:
            page.goto("http://localhost:5000")
            page.wait_for_selector(".container")

            scroll_width = page.evaluate("document.documentElement.scrollWidth")
            client_width = page.evaluate("document.documentElement.clientWidth")

            print(f"Viewport: {client_width}, Scroll: {scroll_width}")

            if scroll_width > client_width:
                # Find elements extending beyond the viewport width
                wide_elements = page.evaluate("""() => {
                    const elements = document.querySelectorAll('*');
                    const wide = [];
                    const vw = document.documentElement.clientWidth;
                    elements.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.right > vw) {
                            wide.push({
                                tag: el.tagName,
                                class: el.className,
                                right: rect.right,
                                width: el.offsetWidth
                            });
                        }
                    });
                    return wide;
                }""")
                print("Wide Elements (Right Edge > Viewport):")
                for el in wide_elements:
                    print(f" - {el['tag']}.{el['class']}: right={el['right']}, width={el['width']}")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_mobile_layout()
