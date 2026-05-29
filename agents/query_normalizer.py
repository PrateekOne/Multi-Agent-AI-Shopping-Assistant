import logging
import re

from config import CONFIG
from llm_client import send_prompt_to_llm

logger = logging.getLogger(__name__)

# Known colloquial/color-coded product names mapped to their real searchable names.
# Checking this table first means zero LLM cost for common cases.
# Add new entries here as you discover them in production.
COLLOQUIAL_MAP = {
    # Pringles — color of can
    "red pringles": "Pringles Original",
    "green pringles": "Pringles Sour Cream Onion",
    "blue pringles": "Pringles BBQ",
    "purple pringles": "Pringles Cheddar Cheese",
    "yellow pringles": "Pringles Salt Vinegar",

    # Lays — color of packet
    "yellow lays": "Lays Classic Salted",
    "red lays": "Lays Magic Masala",
    "blue lays": "Lays Classic Salted",
    "green lays": "Lays American Style Cream Onion",
    "orange lays": "Lays Spanish Tomato Tango",

    # Coca-Cola variants
    "diet coke": "Coca Cola Diet",
    "coke zero": "Coca Cola Zero Sugar",
    "coke light": "Coca Cola Diet",

    # Pepsi variants
    "diet pepsi": "Pepsi Diet",
    "pepsi black": "Pepsi Black",

    # Fanta
    "orange fanta": "Fanta Orange",
    "green fanta": "Fanta Green Apple",

    # Oreo
    "small oreos": "Oreo Mini",
    "mini oreos": "Oreo Mini",
    "big oreos": "Oreo",

    # Dairy Milk
    "big dairy milk": "Cadbury Dairy Milk",
    "small dairy milk": "Cadbury Dairy Milk",

    # Kit Kat
    "green kitkat": "Kit Kat Matcha",
    "red kitkat": "Kit Kat Original",

    # Maggi
    "maggi masala": "Maggi 2-Minute Noodles Masala",
    "maggi red": "Maggi 2-Minute Noodles",
    "yellow maggi": "Maggi 2-Minute Noodles Masala",

    # Amul
    "amul gold": "Amul Gold Full Cream Milk",
    "amul blue": "Amul Taaza Toned Milk",
    "amul green": "Amul Slim Trim Milk",
    "blue amul": "Amul Taaza Toned Milk",
    "gold amul": "Amul Gold Full Cream Milk",

    # Kurkure
    "red kurkure": "Kurkure Masala Munch",
    "green kurkure": "Kurkure Green Chutney",
    "orange kurkure": "Kurkure Hyderabadi Hungama",
}

# Color words that signal a product name might be using informal/visual shorthand
_COLOR_WORDS = frozenset({
    "red", "green", "blue", "yellow", "orange", "purple", "pink",
    "black", "white", "golden", "gold", "silver", "grey", "gray",
})


def normalize_query(item_name: str) -> str:
    """
    Convert a colloquial product name to a proper searchable product name.

    Steps:
    1. Check the local lookup table — zero cost, covers common color-coded products
    2. If the name contains a color word and isn't in the table, ask the LLM
    3. If the LLM fails or it doesn't look colloquial, return the original name

    Examples:
      "red pringles"   -> "Pringles Original"
      "2 litre milk"   -> "milk"  (no color word, passes through)
      "maggi masala"   -> "Maggi 2-Minute Noodles Masala"
    """
    cleaned = item_name.lower().strip()

    # Step 1: exact match in local table
    if cleaned in COLLOQUIAL_MAP:
        result = COLLOQUIAL_MAP[cleaned]
        logger.debug("Query normalized (local table): '%s' -> '%s'", item_name, result)
        return result

    # Step 2: check if any color word appears — only then bother the LLM
    words = set(cleaned.split())
    if not (_COLOR_WORDS & words):
        return item_name

    # Step 3: lightweight LLM call to resolve the colloquial name
    result = _ask_llm(item_name)
    if result and result.lower().strip() != cleaned:
        logger.info("Query normalized (LLM): '%s' -> '%s'", item_name, result)
        return result

    return item_name


def _ask_llm(item_name: str) -> str:
    """
    Ask the LLM to convert an informal product description to a real product name.
    Uses a tiny token budget since we only need the product name back.
    """
    prompt = (
        "You are a product search assistant for an Indian grocery app (Blinkit, Zepto).\n"
        "Convert the user's informal description to the official product name used on these apps.\n\n"
        "Rules:\n"
        "- Colors often refer to packaging color, not product color\n"
        '- "red pringles" = Pringles Original, "green pringles" = Pringles Sour Cream Onion\n'
        '- "yellow lays" = Lays Classic Salted, "red lays" = Lays Magic Masala\n'
        "- Return ONLY the product name, nothing else, no punctuation\n"
        "- If you are not sure, return the input unchanged\n\n"
        f'Input: "{item_name}"\n'
        "Output:"
    )

    try:
        response = send_prompt_to_llm(
            prompt,
            max_tokens=30,       # product name is short — keep this cheap
            temperature=0.0,     # deterministic
        )
        if response:
            # Strip any quotes or extra whitespace the LLM might add
            cleaned_response = re.sub(r'["\']', "", response).strip()
            # Sanity check: reject if the LLM returns something suspiciously long
            if cleaned_response and len(cleaned_response) < 80:
                return cleaned_response
    except Exception as exc:
        logger.debug("LLM normalization failed for '%s': %s", item_name, exc)

    return item_name
