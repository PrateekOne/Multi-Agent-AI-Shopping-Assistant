import logging
import re
import time

from agents.selector_agent import choose_best_product
from utils.playwright_manager import get_browser

logger = logging.getLogger(__name__)


class ZeptoBot:
    def __init__(self):
        self.cart = []
        self.page = None

    def start(self):
        browser = get_browser()
        self.page = browser.new_page()
        self.page.goto("https://www.zeptonow.com")
        self.page.wait_for_timeout(4000)

    def run(self, items, progress):
        if not self.page:
            self.start()

        # Clear whatever is left in the cart from the previous run
        self.clear_cart()

        for item in items:
            item_name = item["name"]
            quantity = int(item.get("amount", 1))

            progress.update(5, f"Zepto: searching '{item_name}'")

            products = self.search_zepto(item_name)
            if not products:
                logger.warning("Zepto: no results for '%s'", item_name)
                continue

            best = choose_best_product(item_name, products)
            if not best:
                logger.warning("Zepto: selector returned None for '%s'", item_name)
                continue

            logger.info("Zepto: selected '%s' @ Rs%s (qty %d)", best["name"], best["price"], quantity)
            progress.update(3, f"Zepto: adding '{best['name']}' x{quantity} @ Rs{best['price']}")

            self.add_to_cart(best, units=quantity)
            self.cart.append({"name": best["name"], "price": best["price"]})

        return self.cart

    def clear_cart(self):
        # Decrement all cart items until the cart is empty.
        # Cap at 100 to avoid an infinite loop if a button never goes away.
        logger.info("Zepto: clearing cart from previous run")
        try:
            attempts = 0
            while attempts < 100:
                minus_btns = self.page.locator(
                    "button[aria-label='Decrease quantity'], "
                    "button[aria-label='Remove item'], "
                    "button[data-testid='decrement-btn']"
                )
                if minus_btns.count() == 0:
                    break
                minus_btns.first.click()
                self.page.wait_for_timeout(400)
                attempts += 1
        except Exception as exc:
            logger.debug("Zepto clear_cart: %s", exc)

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

                # Skip cards that are missing any of the three fields we need
                if name_el.count() == 0 or price_el.count() == 0 or qty_el.count() == 0:
                    continue

                name = name_el.first.inner_text().strip()
                price_text = price_el.first.inner_text()
                price_match = re.search(r"\d+", price_text)
                if not price_match:
                    continue

                products.append({
                    "name": name,
                    "price": int(price_match.group()),
                    "card": card,
                })
            except Exception as exc:
                logger.debug("Zepto: skipping product %d: %s", i, exc)

        return products

    def add_to_cart(self, product, units=1):
        try:
            card = product["card"]
            card.scroll_into_view_if_needed()

            add_btn = card.locator("button:has-text('ADD')")
            if add_btn.count() == 0:
                logger.warning("Zepto: ADD button not found for '%s'", product["name"])
                return

            add_btn.first.click()
            time.sleep(0.8)

            # Keep clicking "+" for quantities above 1
            if units > 1:
                plus_btn = card.locator("button[aria-label='Increase quantity']")
                for _ in range(units - 1):
                    if plus_btn.count() > 0:
                        plus_btn.first.click()
                        time.sleep(0.4)

        except Exception as exc:
            logger.warning("Zepto: failed to add '%s': %s", product["name"], exc)
