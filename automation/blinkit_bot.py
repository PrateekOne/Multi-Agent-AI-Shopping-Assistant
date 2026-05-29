import logging
import re
import time

from agents.quantity_calculator import calculate_units_needed
from agents.query_normalizer import normalize_query
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

        self.clear_cart()

        for item in items:
            item_name = item["name"]
            requested_amount = item.get("amount", 1)
            requested_unit = item.get("unit", "unit")

            # Convert colloquial names to proper searchable names.
            # search_name is used for both the site search AND the ranker query
            # so that relevance scoring is against the real product name.
            # e.g. "green pringles" -> "Pringles Sour Cream Onion" for both.
            search_name = normalize_query(item_name)
            if search_name != item_name:
                progress.update(0, f"Blinkit: '{item_name}' -> searching as '{search_name}'")

            preferred_brand = get_preferred_brand(item_name)

            if preferred_brand:
                item_words = set(search_name.lower().split())
                brand_words = set(preferred_brand.lower().split())
                if item_words <= brand_words:
                    search_query = preferred_brand
                else:
                    search_query = f"{preferred_brand} {search_name}"
                progress.update(5, f"Blinkit: searching '{search_query}' (preferred brand)")
            else:
                search_query = search_name
                progress.update(5, f"Blinkit: searching '{search_query}'")

            products = self.search_blinkit(search_query)
            if not products:
                logger.warning("Blinkit: no results for '%s'", search_query)
                continue

            # Use search_name (the resolved product name) for ranking, not the
            # original colloquial input — this is what fixes "green pringles"
            # picking Original instead of Sour Cream & Onion
            best = choose_best_product(search_name, products)
            if not best:
                logger.warning("Blinkit: selector returned None for '%s'", search_name)
                continue

            units_to_add = calculate_units_needed(requested_amount, requested_unit, best["name"])

            logger.info(
                "Blinkit: selected '%s' @ Rs%s | requested %s %s -> adding %d pack(s)",
                best["name"], best["price"], requested_amount, requested_unit, units_to_add,
            )
            progress.update(3, f"Blinkit: adding '{best['name']}' x{units_to_add} @ Rs{best['price']}")

            self.add_to_cart(best, units=units_to_add)
            self.cart.append({"name": best["name"], "price": best["price"] * units_to_add})

        return self.cart

    def clear_cart(self):
        logger.info("Blinkit: clearing cart from previous run")
        try:
            attempts = 0
            while attempts < 100:
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
