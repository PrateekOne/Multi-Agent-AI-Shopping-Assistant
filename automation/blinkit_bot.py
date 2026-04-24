from playwright.sync_api import sync_playwright
import re
import time
from utils.playwright_manager import get_browser
from agents.selector_agent import choose_best_product

class BlinkitBot:
    def __init__(self):
        self.cart = []
        self.playwright = None
        self.browser = None
        self.page = None

    


    def start(self):
        self.browser = get_browser()
        self.page = self.browser.new_page()   # NEW TAB
        self.page.goto("https://blinkit.com")
        self.page.wait_for_timeout(4000)

    def run(self, items, progress):
        if not self.page:
            self.start()

        for item in items:
            progress.update(5, f"Blinkit searching {item['name']}")

            search = self.page.locator("input[placeholder*='Search']").first
            search.wait_for(state="visible", timeout=10000)

            search.click()
            search.fill("")
            search.fill(item["name"])
            search.press("Enter")

            self.page.wait_for_selector(
                "div.tw-text-300.tw-font-semibold",
                timeout=15000
            )

            products = self.extract_products(self.page)

            if not products:
                continue

            best = choose_best_product(item["name"], products)

            best["card"].scroll_into_view_if_needed()
            add_btn = best["card"].locator("text=ADD")

            if add_btn.count() > 0:
                add_btn.first.click()
                time.sleep(1)

            self.cart.append({
            "name": best["name"],
            "price": best["price"]
            })

        return self.cart

    def extract_products(self, page):
        name_elements = page.locator(
            "div.tw-text-300.tw-font-semibold.tw-line-clamp-2"
        )

        count = name_elements.count()
        products = []

        for i in range(count):
            try:
                name_el = name_elements.nth(i)
                name = name_el.inner_text().strip()

                card = name_el.locator("xpath=ancestor::div[@role='button'][1]")
                text = card.inner_text().lower()

                price_match = re.search(r"₹\s*(\d+)", text)
                qty_match = re.search(r"(\d+(?:\.\d+)?)\s*(ml|l|kg|g)", text)

                if not price_match or not qty_match:
                    continue

                price = int(price_match.group(1))

                amount = float(qty_match.group(1))
                unit = qty_match.group(2)

                if unit == "ml":
                    quantity = amount / 1000
                    unit = "l"
                elif unit == "g":
                    quantity = amount / 1000
                    unit = "kg"
                else:
                    quantity = amount

                products.append({
                    "name": name,
                    "price": price,
                    "card": card
                })

            except:
                continue

        return products

    def close(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()