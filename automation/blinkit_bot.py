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
        self.page = None

    def start(self):
        browser = get_browser()
        self.page = browser.new_page()
        self.page.goto("https://blinkit.com")
        self.page.wait_for_timeout(4000)

    def run(self, items, progress):
        if not self.page:
            self.start()

        # Clear whatever is left in the cart from the previous run
        self.clear_cart()

        for item in items:
            item_name = item["name"]
            quantity = int(item.get("amount", 1))
            preferred_brand = get_preferred_brand(item_name)

            # Build search query — if brand string already contains the item
            # words we use the brand alone, otherwise prepend it
            if preferred_brand:
                item_words = set(item_name.lower().split())
                brand_words = set(preferred_brand.lower().split())
                if item_words <= brand_words:
                    search_query = preferred_brand
                else:
                    search_query = f"{preferred_brand} {item_name}"
                progress.update(5, f"Blinkit: searching '{search_query}' (preferred brand)")
            else:
                search_query = item_name
                progress.update(5, f"Blinkit: searching '{search_query}'")

            products = self.search_blinkit(search_query)
            if not products:
                logger.warning("Blinkit: no results for '%s'", search_query)
                continue

            best = choose_best_product(item_name, products)
            if not best:
                logger.warning("Blinkit: selector returned None for '%s'", item_name)
                continue

            logger.info("Blinkit: selected '%s' @ Rs%s (qty %d)", best["name"], best["price"], quantity)
            progress.update(3, f"Blinkit: adding '{best['name']}' x{quantity} @ Rs{best['price']}")

            self.add_to_cart(best, units=quantity)
            self.cart.append({"name": best["name"], "price": best["price"]})

        return self.cart

    def clear_cart(self):
        # Keep clicking the stepper decrement button until there are no items left.
        # We cap at 100 clicks as a safety net in case a selector never disappears.
        logger.info("Blinkit: clearing cart from previous run")
        try:
            attempts = 0
            while attempts < 100:
                # Blinkit uses a button with a minus icon inside cart items
                minus_btns = self.page.locator(
                    "button[class*='decrement'], "
                    "button[aria-label*='Remove'], "
                    "button[aria-label*='Decrease']"
                )
                if minus_btns.count() == 0:
                    break
                minus_btns.first.click()
                self.page.wait_for_timeout(400)
                attempts += 1
        except Exception as exc:
            # Cart may already be empty or layout changed — not critical
            logger.debug("Blinkit clear_cart: %s", exc)

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
                products.append({
                    "name": name,
                    "price": int(price_match.group(1)),
                    "card": card,
                })
            except Exception as exc:
                logger.debug("Blinkit: skipping product %d: %s", i, exc)

        return products

    def add_to_cart(self, product, units=1):
        try:
            card = product["card"]
            card.scroll_into_view_if_needed()

            add_btn = card.locator("text=ADD")
            if add_btn.count() == 0:
                logger.warning("Blinkit: ADD button not found for '%s'", product["name"])
                return

            add_btn.first.click()
            time.sleep(0.8)

            # Click the "+" stepper for any quantity above 1
            if units > 1:
                plus_btn = card.locator(
                    "button[aria-label*='Increase'], "
                    "button[class*='increment']"
                )
                for _ in range(units - 1):
                    if plus_btn.count() > 0:
                        plus_btn.first.click()
                        time.sleep(0.4)

        except Exception as exc:
            logger.warning("Blinkit: failed to add '%s': %s", product["name"], exc)
