import logging
import re

from agents.quantity_calculator import calculate_units_needed
from agents.query_normalizer import normalize_query
from agents.selector_agent import choose_best_product
from utils.playwright_manager import get_browser

logger = logging.getLogger(__name__)

# Confirmed from live Zepto stepper HTML:
#
#   <button data-mode="edlp">                    <- outer wrapper
#     <div class="ckLsUx">
#       <button aria-label="Decrease quantity">  <- confirmed
#       <span class="cZrvL8">1</span>
#       <button aria-label="Increase quantity">  <- confirmed
#     </div>
#   </button>
#
# NOTE: nesting <button> inside <button> is invalid HTML. Chromium's parser
# implicitly closes the outer button when it sees the inner button tag, so
# the aria-label buttons may become siblings of the outer wrapper in the
# rendered DOM — but they stay inside the <a.B4vNQ> product card.
# We try card-relative first, then escalate through fallbacks.

_CARD      = "a.B4vNQ"                              # update if Zepto redeploys
_ADD_BTN   = "button:has-text('ADD')"
_STEPPER   = "button[data-mode='edlp']"             # outer wrapper = item in cart
_PLUS_BTN  = "button[aria-label='Increase quantity']"
_MINUS_BTN = "button[aria-label='Decrease quantity']"


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

        self.clear_cart()

        for item in items:
            item_name        = item["name"]
            requested_amount = item.get("amount", 1)
            requested_unit   = item.get("unit", "unit")

            search_name = normalize_query(item_name)
            if search_name != item_name:
                progress.update(0, f"Zepto: '{item_name}' -> searching as '{search_name}'")

            progress.update(5, f"Zepto: searching '{search_name}'")

            products = self.search_zepto(search_name)
            if not products:
                logger.warning("Zepto: no results for '%s'", search_name)
                continue

            best = choose_best_product(search_name, products)
            if not best:
                logger.warning("Zepto: selector returned None for '%s'", search_name)
                continue

            units_to_add = calculate_units_needed(requested_amount, requested_unit, best["name"])
            logger.info(
                "Zepto: selected '%s' @ Rs%s | requested %s %s -> adding %d pack(s)",
                best["name"], best["price"], requested_amount, requested_unit, units_to_add,
            )
            progress.update(3, f"Zepto: adding '{best['name']}' x{units_to_add} @ Rs{best['price']}")

            self.add_to_cart(best, units=units_to_add)
            self.cart.append({"name": best["name"], "price": best["price"] * units_to_add})

        return self.cart

    def clear_cart(self):
        logger.info("Zepto: clearing cart from previous run")
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
            logger.debug("Zepto clear_cart: %s", exc)

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

    def search_zepto(self, item):
        try:
            search = self.page.locator("input[placeholder*='Search']").first
            search.wait_for(state="visible", timeout=20000)
            search.click()
            search.fill("")
            search.fill(item)
            search.press("Enter")
            self.page.wait_for_selector(_CARD, timeout=20000)
            return self.extract_products()
        except Exception as exc:
            logger.error("Zepto search failed for '%s': %s", item, exc)
            return []

    def extract_products(self):
        cards    = self.page.locator(_CARD)
        count    = cards.count()
        products = []

        for i in range(count):
            try:
                card     = cards.nth(i)
                name_el  = card.locator("div[data-slot-id='ProductName'] span")
                price_el = card.locator("div[data-slot-id='EdlpPrice'] span")
                qty_el   = card.locator("div[data-slot-id='PackSize'] span")

                if name_el.count() == 0 or price_el.count() == 0 or qty_el.count() == 0:
                    continue

                name        = name_el.first.inner_text().strip()
                price_text  = price_el.first.inner_text()
                price_match = re.search(r"\d+", price_text)
                if not price_match:
                    continue

                # Append the pack size (e.g. "500 ml") to the product name so
                # calculate_units_needed can divide user's requested volume by pack size
                pack_size = qty_el.first.inner_text().strip()
                if pack_size and pack_size.lower() not in name.lower():
                    name = f"{name} {pack_size}"

                products.append({
                    "name":  name,
                    "price": int(price_match.group()),
                    "card":  card,
                })
            except Exception as exc:
                logger.debug("Zepto: skipping product %d: %s", i, exc)

        return products

    def _find_plus_btn(self, card):
        selectors = [
            "button[aria-label='Increase quantity']",
            "[aria-label='Increase quantity']",
            "button:has(svg)",
        ]

        for sel in selectors:
            try:
                btn = card.locator(sel)
                if btn.count() > 0:
                    return btn.last
            except Exception:
                pass

        return None

    def add_to_cart(self, product, units=1):
        try:
            card = product["card"]
            card.scroll_into_view_if_needed()
            self.page.wait_for_timeout(500)

            add_btn = card.locator(_ADD_BTN)

            if add_btn.count() > 0:
                add_btn.first.click(force=True)

                for _ in range(20):
                    plus_btn = card.locator(
                        "button[aria-label='Increase quantity']"
                    )
                    if plus_btn.count() > 0:
                        break
                    self.page.wait_for_timeout(250)

            if units <= 1:
                return

            for step in range(units - 1):

                plus_btn = card.locator(
                    "button[aria-label='Increase quantity']"
                )

                if plus_btn.count() == 0:
                    plus_btn = self._find_plus_btn(card)

                if plus_btn is None or plus_btn.count() == 0:
                    logger.warning(
                        "Zepto: plus button missing at step %d/%d for '%s'",
                        step + 1,
                        units - 1,
                        product["name"],
                    )
                    break

                plus_btn.first.click(force=True)
                self.page.wait_for_timeout(700)

        except Exception as exc:
            logger.warning(
                "Zepto: failed to add '%s': %s",
                product["name"],
                exc,
            )

