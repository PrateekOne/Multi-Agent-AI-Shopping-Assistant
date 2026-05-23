"""
automation/blinkit_bot.py

Playwright bot for Blinkit.
Core automation logic is unchanged from original.
Changes: structured logging, explicit exception logging (no silent swallowing).
"""

from __future__ import annotations

import logging
import re
import time

from agents.selector_agent import choose_best_product
from memory import get_preferred_brand
from utils.playwright_manager import get_browser

logger = logging.getLogger(__name__)


class BlinkitBot:
    def __init__(self):
        self.cart = []
        self.browser = None
        self.page = None

    def start(self):
        self.browser = get_browser()
        self.page = self.browser.new_page()
        self.page.goto("https://blinkit.com")
        self.page.wait_for_timeout(4000)

    def run(self, items, progress):
        if not self.page:
            self.start()

        for item in items:
            item_name = item["name"]
            preferred_brand = get_preferred_brand(item_name)

            if preferred_brand:
                search_query = f"{preferred_brand} {item_name}"
                progress.update(5, f"Blinkit: searching '{search_query}' (preferred brand)")
            else:
                search_query = item_name
                progress.update(5, f"Blinkit: searching '{search_query}'")

            products = self.search_blinkit(search_query)

            if not products:
                logger.warning("Blinkit: no products found for '%s'", search_query)
                continue

            logger.info("Blinkit: found %d products for '%s'", len(products), search_query)

            best = choose_best_product(item_name, products)

            if not best:
                logger.warning("Blinkit: selector returned None for '%s'", item_name)
                continue

            logger.info("Blinkit: selected '%s' @ Rs%s", best["name"], best["price"])
            progress.update(3, f"Blinkit: adding '{best['name']}' @ Rs{best['price']}")

            self.add_to_cart(best)
            self.cart.append({"name": best["name"], "price": best["price"]})

        return self.cart

    def search_blinkit(self, item):
        try:
            search = self.page.locator("input[placeholder*='Search']").first
            search.wait_for(state="visible", timeout=15000)
            search.click()
            search.fill("")
            search.fill(item)
            search.press("Enter")
            self.page.wait_for_selector(
                "div.tw-text-300.tw-font-semibold.tw-line-clamp-2",
                timeout=15000,
            )
            return self.extract_products()
        except Exception as exc:
            logger.error("Blinkit search failed for '%s': %s", item, exc)
            return []

    def extract_products(self):
        name_elements = self.page.locator(
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
                if not price_match:
                    continue
                price = int(price_match.group(1))
                products.append({"name": name, "price": price, "card": card})

            except Exception as exc:
                logger.debug("Blinkit: skipping product %d due to: %s", i, exc)
                continue

        return products

    def add_to_cart(self, product):
        try:
            card = product["card"]
            card.scroll_into_view_if_needed()
            add_btn = card.locator("text=ADD")
            if add_btn.count() > 0:
                add_btn.first.click()
                time.sleep(1)
        except Exception as exc:
            logger.warning("Blinkit: failed to add '%s' to cart: %s", product["name"], exc)
