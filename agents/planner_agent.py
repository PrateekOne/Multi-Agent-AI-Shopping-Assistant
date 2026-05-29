import json
import re

from llm_client import send_prompt_to_llm


def extract_items(prompt):
    prompt = prompt.lower().strip()

    llm_prompt = f"""
Return ONLY valid JSON. No text before or after.

Structure exactly like this:
{{
"budget": null,
"priority_items": [],
"item_quantities": {{}}
}}

Rules:
- Split items only by "and" or comma.
- Keep combined names as ONE item (e.g. "lays magic masala", "red pringles").
- Do NOT translate or interpret color names or brand nicknames — keep them exactly as the user wrote them.
- If input is a dish name, convert to its simple ingredients (e.g. "biryani" -> rice, chicken, oil, onions, spices).
- If quantity missing: amount=1, unit="unit"
- Units allowed: ml, ltr, litre, liter, kg, g, gm, pcs, pack, unit
- For eggs and similar countable items use unit="pcs"
- budget must be a number or null

IMPORTANT:
Every item in "priority_items" MUST also appear in "item_quantities".

User input:
{prompt}
"""

    response = send_prompt_to_llm(llm_prompt)

    try:
        response = clean_json(response)
        data = json.loads(response)

        if "priority_items" not in data or "item_quantities" not in data:
            raise ValueError("Invalid format")

        return normalize_output(data)

    except Exception:
        return fallback_parser(prompt)


def clean_json(text):
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    text = text[start:end]
    text = text.replace("'", '"')
    return text


def normalize_output(data):
    items = data.get("priority_items", [])
    quantities = data.get("item_quantities", {})
    fixed_quantities = {}

    for item in items:
        if item not in quantities:
            fixed_quantities[item] = {"amount": 1, "unit": "unit"}
        else:
            q = quantities[item]
            fixed_quantities[item] = {
                "amount": q.get("amount", 1),
                "unit": q.get("unit", "unit"),
            }

    return {
        "budget": data.get("budget", None),
        "priority_items": items,
        "item_quantities": fixed_quantities,
    }


# Matches an optional leading quantity like "2 litre", "500g", "1.5 kg" at the
# start of an item string. Used by fallback_parser when the LLM is unavailable.
_LEADING_QTY_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*"
    r"(ml|l\b|ltr|litres?|liters?|kg|g\b|gm|gms?|pcs?|packs?|pieces?|units?)?\s+(.+)$",
    re.IGNORECASE,
)

# Canonical unit names for the unit strings the regex can capture
_UNIT_CANONICAL = {
    "ml": "ml",
    "l": "ltr", "ltr": "ltr",
    "litre": "ltr", "litres": "ltr", "liter": "ltr", "liters": "ltr",
    "kg": "kg",
    "g": "g", "gm": "g", "gms": "g",
    "pc": "pcs", "pcs": "pcs",
    "pack": "pack", "packs": "pack",
    "piece": "pcs", "pieces": "pcs",
    "unit": "unit", "units": "unit",
}


def fallback_parser(prompt):
    """
    Regex-based parser used when the LLM is offline or returns bad JSON.

    Handles quantity prefixes so "2 litre milk" correctly produces
    {name: "milk", amount: 2, unit: "ltr"} instead of losing the quantity.
    """
    parts = prompt.replace(",", " and ").split("and")
    items = []
    quantities = {}

    for part in parts:
        part = part.strip()
        if not part:
            continue

        match = _LEADING_QTY_RE.match(part)
        if match:
            raw_amount = match.group(1)
            raw_unit = match.group(2) or "unit"
            name = match.group(3).strip()
            amount = float(raw_amount)
            unit = _UNIT_CANONICAL.get(raw_unit.lower(), "unit")
        else:
            # No leading quantity — treat whole string as item name, qty = 1
            name = part
            amount = 1
            unit = "unit"

        items.append(name)
        quantities[name] = {"amount": amount, "unit": unit}

    return {
        "budget": None,
        "priority_items": items,
        "item_quantities": quantities,
    }
