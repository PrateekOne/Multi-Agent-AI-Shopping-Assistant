import logging
import re

from config import CONFIG
from llm_client import send_prompt_to_llm

logger = logging.getLogger(__name__)

# Known colloquial/color-coded product names -> real searchable names.
# Zero LLM cost for anything in this table.
# Packet colors for Lays in India:
#   Yellow = Classic Salted,  Red/Blue = Magic Masala,
#   Orange = Spanish Tomato,  Green = Cream & Onion
COLLOQUIAL_MAP = {
    # Pringles — color of can lid
    "red pringles":    "Pringles Original",
    "green pringles":  "Pringles Sour Cream Onion",
    "blue pringles":   "Pringles BBQ",
    "purple pringles": "Pringles Cheddar Cheese",
    "yellow pringles": "Pringles Salt Vinegar",

    # Lays — packet color (Magic Masala packet is red AND blue)
    "yellow lays":  "Lays Classic Salted",
    "red lays":     "Lays Magic Masala",
    "blue lays":    "Lays Magic Masala",      # blue/red packet = Magic Masala
    "green lays":   "Lays American Style Cream Onion",
    "orange lays":  "Lays Spanish Tomato Tango",

    # Coca-Cola variants
    "diet coke":  "Coca Cola Diet",
    "coke zero":  "Coca Cola Zero Sugar",
    "coke light": "Coca Cola Diet",

    # Pepsi variants
    "diet pepsi": "Pepsi Diet",
    "pepsi black": "Pepsi Black",

    # Fanta
    "orange fanta": "Fanta Orange",
    "green fanta":  "Fanta Green Apple",

    # Oreo
    "small oreos": "Oreo Mini",
    "mini oreos":  "Oreo Mini",
    "big oreos":   "Oreo",

    # Dairy Milk
    "big dairy milk":   "Cadbury Dairy Milk",
    "small dairy milk": "Cadbury Dairy Milk",

    # Kit Kat
    "green kitkat": "Kit Kat Matcha",
    "red kitkat":   "Kit Kat Original",

    # Maggi
    "maggi masala": "Maggi 2-Minute Noodles Masala",
    "red maggi":    "Maggi 2-Minute Noodles",
    "yellow maggi": "Maggi 2-Minute Noodles Masala",

    # Amul milk — packet color indicates fat content
    "amul gold":  "Amul Gold Full Cream Milk",
    "amul blue":  "Amul Taaza Toned Milk",
    "amul green": "Amul Slim Trim Milk",
    "blue amul":  "Amul Taaza Toned Milk",
    "gold amul":  "Amul Gold Full Cream Milk",

    # Kurkure
    "red kurkure":    "Kurkure Masala Munch",
    "green kurkure":  "Kurkure Green Chutney",
    "orange kurkure": "Kurkure Hyderabadi Hungama",
}

_COLOR_WORDS = frozenset({
    "red", "green", "blue", "yellow", "orange", "purple", "pink",
    "black", "white", "golden", "gold", "silver", "grey", "gray",
})


def normalize_query(item_name: str) -> str:
    """
    Convert a colloquial product description to its proper searchable name.

    1. Check local table (zero LLM cost)
    2. If a color word is present and no table match, ask LLM (30-token budget)
    3. If LLM fails, return original unchanged
    """
    cleaned = item_name.lower().strip()

    if cleaned in COLLOQUIAL_MAP:
        result = COLLOQUIAL_MAP[cleaned]
        logger.debug("Normalized (table): '%s' -> '%s'", item_name, result)
        return result

    words = set(cleaned.split())
    if not (_COLOR_WORDS & words):
        return item_name

    result = _ask_llm(item_name)
    if result and result.lower().strip() != cleaned:
        logger.info("Normalized (LLM): '%s' -> '%s'", item_name, result)
        return result

    return item_name


def _ask_llm(item_name: str) -> str:
    prompt = (
        "You are a product search assistant for an Indian grocery app.\n"
        "Convert the informal description to the official product name.\n\n"
        "Rules:\n"
        "- Colors refer to packaging: 'red pringles'=Original, 'green pringles'=Sour Cream Onion\n"
        "- Lays Magic Masala packet is blue+red. 'blue lays' or 'red lays' = Lays Magic Masala\n"
        "- 'yellow lays' = Lays Classic Salted\n"
        "- Return ONLY the product name, no punctuation\n"
        "- If unsure, return the input unchanged\n\n"
        f'Input: "{item_name}"\n'
        "Output:"
    )
    try:
        response = send_prompt_to_llm(prompt, max_tokens=30, temperature=0.0)
        if response:
            cleaned = re.sub(r'["\']', "", response).strip()
            if cleaned and len(cleaned) < 80:
                return cleaned
    except Exception as exc:
        logger.debug("LLM normalization failed for '%s': %s", item_name, exc)
    return item_name
