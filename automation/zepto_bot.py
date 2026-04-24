from utils.playwright_manager import get_browser
from llm_client import send_prompt_to_llm
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

            progress.update(5, f"Zepto searching {target_name}")

            products = self.search_zepto(target_name)

            if not products:
                continue

            # ✅ STEP 1: Try first result
            first = products[0]

            if self.is_match(target_name, first["name"]):
                best = first
            else:
                # ✅ STEP 2: Fallback to LLM
                best = self.choose_with_llm(target_name, products)

            self.add_to_cart(best)

            self.cart.append({
                "name": best["name"],
                "price": best["price"]
            })

        return self.cart

    # ---------------- SEARCH ---------------- #

    def search_zepto(self, item):
        search = self.page.locator("input[placeholder*='Search']").first

        search.wait_for(state="visible", timeout=20000)

        search.click()
        search.fill("")
        search.fill(item)
        search.press("Enter")

        self.page.wait_for_selector("a.B4vNQ", timeout=20000)

        return self.extract_products()

    # ---------------- EXTRACT ---------------- #

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

                products.append({
                    "name": name,
                    "price": price,
                    "card": card
                })

            except:
                continue

        return products

    # ---------------- MATCH CHECK ---------------- #

    def is_match(self, target, candidate):
        target = target.lower()
        candidate = candidate.lower()

        # basic fuzzy match
        return target in candidate or candidate in target

    # ---------------- LLM FALLBACK ---------------- #

    def choose_with_llm(self, item, products):
        subset = products[:6]
        names = [p["name"] for p in subset]

        prompt = f"""
Pick the best matching product for: {item}

Return ONLY one exact name from the list.

Options:
{names}
"""

        response = send_prompt_to_llm(prompt)

        if not response:
            return subset[0]

        chosen = self.clean_response(response)

        for p in subset:
            if chosen.lower() in p["name"].lower():
                return p

        return subset[0]

    def clean_response(self, text):
        text = text.strip()
        text = text.replace("\n", "")
        text = text.replace('"', "")
        return text

    # ---------------- ADD TO CART ---------------- #

    def add_to_cart(self, product, units=1):
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