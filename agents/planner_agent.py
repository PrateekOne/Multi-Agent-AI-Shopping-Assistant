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
    fixed = {}
    for item in items:
        q = quantities.get(item, {})
        fixed[item] = {
            "amount": q.get("amount", 1),
            "unit":   q.get("unit", "unit"),
        }
    return {
        "budget":          data.get("budget", None),
        "priority_items":  items,
        "item_quantities": fixed,
    }


# Regex: optional leading "<number> <unit>" before the actual item name.
# Handles: "2 litres of milk", "500g flour", "3 packs biscuits"
_LEADING_QTY_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*"
    r"(ml|l\b|ltr|litres?|liters?|kg|g\b|gm|gms?|pcs?|packs?|pieces?|units?)?"
    r"\s+(.+)$",
    re.IGNORECASE,
)

_UNIT_CANONICAL = {
    "ml": "ml",
    "l": "ltr", "ltr": "ltr", "litre": "ltr", "litres": "ltr",
    "liter": "ltr", "liters": "ltr",
    "kg": "kg", "g": "g", "gm": "g", "gms": "g",
    "pc": "pcs", "pcs": "pcs",
    "pack": "pack", "packs": "pack",
    "piece": "pcs", "pieces": "pcs",
    "unit": "unit", "units": "unit",
}

# Words that appear between a quantity and the actual item name.
# "2 liters OF milk" — strip "of" so the name becomes "milk" not "of milk".
_LEADING_PREPS = {"of", "from", "the", "a", "an", "some", "fresh"}


def _clean_name(name: str) -> str:
    """Strip leading prepositions/articles that follow a quantity expression."""
    words = name.split()
    while words and words[0].lower() in _LEADING_PREPS:
        words.pop(0)
    return " ".join(words) if words else name


def fallback_parser(prompt):
    """
    Regex-based parser used when the LLM is offline or returns bad JSON.

    Correctly handles:
      "2 liters of milk"   -> name="milk",    amount=2,   unit="ltr"
      "500g of flour"      -> name="flour",   amount=500, unit="g"
      "3 packs biscuits"   -> name="biscuits", amount=3,  unit="pack"
      "milk"               -> name="milk",    amount=1,   unit="unit"
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
            amount   = float(match.group(1))
            raw_unit = match.group(2) or "unit"
            unit     = _UNIT_CANONICAL.get(raw_unit.lower(), "unit")
            name     = _clean_name(match.group(3).strip())
        else:
            name   = part
            amount = 1
            unit   = "unit"

        if not name:
            continue

        items.append(name)
        quantities[name] = {"amount": amount, "unit": unit}

    return {
        "budget":          None,
        "priority_items":  items,
        "item_quantities": quantities,
    }
