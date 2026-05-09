from utils.playwright_manager import get_browser
from agents.selector_agent import choose_best_product

import re
import time


class ZeptoBot:
    def __init__(self):
        self.cart = []
        self.browser = None
        self.page = None

    def start(self):
        self.browser = get_browser()

        self.page = self.browser.new_page()

        self.page.goto("https://www.zeptonow.com")

        self.page.wait_for_timeout(4000)

    def run(self, items, progress):
        if not self.page:
            self.start()

        for item in items:

            target_name = item["name"]

            progress.update(
                5,
                f"Zepto searching: {target_name}"
            )

            products = self.search_zepto(target_name)

            if not products:
                continue

            best = choose_best_product(target_name, products)

            if not best:
                continue

            self.add_to_cart(best)

            self.cart.append({
                "name": best["name"],
                "price": best["price"]
            })

        return self.cart

    def search_zepto(self, item):
        search = self.page.locator(
            "input[placeholder*='Search']"
        ).first

        search.wait_for(state="visible", timeout=20000)

        search.click()

        search.fill("")

        search.fill(item)

        search.press("Enter")

        self.page.wait_for_selector(
            "a.B4vNQ",
            timeout=20000
        )

        return self.extract_products()

    def extract_products(self):
        cards = self.page.locator("a.B4vNQ")

        count = cards.count()

        products = []

        for i in range(count):
            try:
                card = cards.nth(i)

                name_el = card.locator(
                    "div[data-slot-id='ProductName'] span"
                )

                price_el = card.locator(
                    "div[data-slot-id='EdlpPrice'] span"
                )

                qty_el = card.locator(
                    "div[data-slot-id='PackSize'] span"
                )

                if (
                    name_el.count() == 0
                    or price_el.count() == 0
                    or qty_el.count() == 0
                ):
                    continue

                name = name_el.first.inner_text().strip()

                price_text = price_el.first.inner_text()

                price_match = re.search(r"\d+", price_text)

                if not price_match:
                    continue

                price = int(price_match.group())

                products.append({
                    "name": name,
                    "price": price,
                    "card": card
                })

            except:
                continue

        return products

    def add_to_cart(self, product, units=1):
        card = product["card"]

        card.scroll_into_view_if_needed()

        add_btn = card.locator("button:has-text('ADD')")

        if add_btn.count() > 0:
            add_btn.first.click()

            time.sleep(1)

        if units > 1:
            plus_btn = card.locator(
                "button[aria-label='Increase quantity']"
            )

            for _ in range(units - 1):
                if plus_btn.count() > 0:
                    plus_btn.first.click()

                    time.sleep(0.5)