"""
automation/zepto_bot.py

Playwright bot for Zepto.
Core automation logic is unchanged from original.
Changes: structured logging, explicit exception logging (no silent swallowing).
"""

from __future__ import annotations

import logging
import re
import time

from agents.selector_agent import choose_best_product
from utils.playwright_manager import get_browser

logger = logging.getLogger(__name__)


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
            progress.update(5, f"Zepto: searching '{target_name}'")

            products = self.search_zepto(target_name)

            if not products:
                logger.warning("Zepto: no products found for '%s'", target_name)
                continue

            logger.info("Zepto: found %d products for '%s'", len(products), target_name)

            best = choose_best_product(target_name, products)

            if not best:
                logger.warning("Zepto: selector returned None for '%s'", target_name)
                continue

            logger.info("Zepto: selected '%s' @ Rs%s", best["name"], best["price"])
            progress.update(3, f"Zepto: adding '{best['name']}' @ Rs{best['price']}")

            self.add_to_cart(best)
            self.cart.append({"name": best["name"], "price": best["price"]})

        return self.cart

    def search_zepto(self, item):
        try:
            search = self.page.locator("input[placeholder*='Search']").first
            search.wait_for(state="visible", timeout=20000)
            search.click()
            search.fill("")
            search.fill(item)
            search.press("Enter")
            self.page.wait_for_selector("a.B4vNQ", timeout=20000)
            return self.extract_products()
        except Exception as exc:
            logger.error("Zepto search failed for '%s': %s", item, exc)
            return []

    def extract_products(self):
        cards = self.page.locator("a.B4vNQ")
        count = cards.count()
        products = []

        for i in range(count):
            try:
                card = cards.nth(i)

                name_el = card.locator("div[data-slot-id='ProductName'] span")
                price_el = card.locator("div[data-slot-id='EdlpPrice'] span")
                qty_el = card.locator("div[data-slot-id='PackSize'] span")

                if name_el.count() == 0 or price_el.count() == 0 or qty_el.count() == 0:
                    continue

                name = name_el.first.inner_text().strip()
                price_text = price_el.first.inner_text()
                price_match = re.search(r"\d+", price_text)

                if not price_match:
                    continue

                price = int(price_match.group())
                products.append({"name": name, "price": price, "card": card})

            except Exception as exc:
                logger.debug("Zepto: skipping product %d due to: %s", i, exc)
                continue

        return products

    def add_to_cart(self, product, units=1):
        try:
            card = product["card"]
            card.scroll_into_view_if_needed()
            add_btn = card.locator("button:has-text('ADD')")
            if add_btn.count() > 0:
                add_btn.first.click()
                time.sleep(1)

            if units > 1:
                plus_btn = card.locator("button[aria-label='Increase quantity']")
                for _ in range(units - 1):
                    if plus_btn.count() > 0:
                        plus_btn.first.click()
                        time.sleep(0.5)
        except Exception as exc:
            logger.warning("Zepto: failed to add '%s' to cart: %s", product["name"], exc)
