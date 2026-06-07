import logging
import re

from agents.quantity_calculator import calculate_units_needed
from agents.query_normalizer import normalize_query
from agents.selector_agent import choose_best_product
from memory import get_preferred_brand
from utils.playwright_manager import get_browser

logger = logging.getLogger(__name__)

_PLUS_BTN = "button:has(span[class*='icon-plus'])"
_MINUS_BTN = "button:has(span[class*='icon-minus'])"
_ADD_BTN = "text=ADD"

# Matches a size/weight anywhere in a string, e.g. "500ml", "1 kg", "6 pcs"
_SIZE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:ml|l\b|ltr|litres?|g\b|gm|gms?|kg|kgs?|pcs?|packs?)",
    re.IGNORECASE,
)


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
            item_name        = item["name"]
            requested_amount = item.get("amount", 1)
            requested_unit   = item.get("unit", "unit")

            search_name = normalize_query(item_name)
            if search_name != item_name:
                progress.update(0, f"Blinkit: '{item_name}' -> searching as '{search_name}'")

            preferred_brand = get_preferred_brand(item_name)
            if preferred_brand:
                item_words  = set(search_name.lower().split())
                brand_words = set(preferred_brand.lower().split())
                search_query = preferred_brand if item_words <= brand_words else f"{preferred_brand} {search_name}"
                progress.update(5, f"Blinkit: searching '{search_query}' (preferred brand)")
            else:
                search_query = search_name
                progress.update(5, f"Blinkit: searching '{search_query}'")

            products = self.search_blinkit(search_query)
            if not products:
                logger.warning("Blinkit: no results for '%s'", search_query)
                continue

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
            self._open_cart_if_collapsed()
            attempts = 0
            while attempts < 100:
                minus_btns = self.page.locator(_MINUS_BTN)
                if minus_btns.count() == 0:
                    break
                minus_btns.first.click()
                self.page.wait_for_timeout(400)
                attempts += 1
        except Exception as exc:
            logger.debug("Blinkit clear_cart: %s", exc)

    def _open_cart_if_collapsed(self):
        try:
            view_cart = self.page.locator(
                "text=View Cart, text=Go to Cart, button:has-text('item')"
            ).first
            if view_cart.is_visible(timeout=1500):
                view_cart.click()
                self.page.wait_for_timeout(1000)
        except Exception:
            pass

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
        count    = name_elements.count()
        products = []

        for i in range(count):
            try:
                name_el = name_elements.nth(i)
                name    = name_el.inner_text().strip()
                card    = name_el.locator("xpath=ancestor::div[@role='button'][1]")
                text    = card.inner_text()

                price_match = re.search(r"₹\s*(\d+)", text)
                if not price_match:
                    continue

                # Blinkit often shows the pack size (e.g. "500 ml") as a
                # separate line below the product name — it's in the card text
                # but not in the name element. Appending it to the name lets
                # the quantity calculator do correct unit division later.
                if not _SIZE_RE.search(name):
                    size_match = _SIZE_RE.search(text)
                    if size_match:
                        name = f"{name} {size_match.group(0).strip()}"

                products.append({
                    "name":  name,
                    "price": int(price_match.group(1)),
                    "card":  card,
                })
            except Exception as exc:
                logger.debug("Blinkit: skipping product %d: %s", i, exc)

        return products

    def add_to_cart(self, product, units=1):
        try:
            card    = product["card"]
            card.scroll_into_view_if_needed()
            add_btn = card.locator(_ADD_BTN)

            if add_btn.count() > 0:
                add_btn.first.click()
                try:
                    card.locator(_PLUS_BTN).first.wait_for(state="visible", timeout=3000)
                except Exception:
                    self.page.wait_for_timeout(1000)
            else:
                if card.locator(_PLUS_BTN).count() == 0:
                    logger.warning("Blinkit: neither ADD nor stepper for '%s'", product["name"])
                    return

            for i in range(units - 1):
                plus_btn = card.locator(_PLUS_BTN)
                if plus_btn.count() == 0:
                    logger.warning("Blinkit: plus gone at step %d/%d for '%s'", i + 1, units - 1, product["name"])
                    break
                plus_btn.first.click()
                self.page.wait_for_timeout(350)

        except Exception as exc:
            logger.warning("Blinkit: failed to add '%s': %s", product["name"], exc)
