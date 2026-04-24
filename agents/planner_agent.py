from llm_client import send_prompt_to_llm
import json


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
- Keep combined names as ONE item (e.g. "lays magic masala").
- If input is a dish, convert to simple ingredients (rice, chicken, oil, onions, spices).
- If quantity missing: amount=1, unit="unit"
- Units allowed: ml, ltr, kg, g, unit
- budget must be number or null

IMPORTANT:
Every item in "priority_items" MUST also appear in "item_quantities".

User input:
{prompt}
"""

    response = send_prompt_to_llm(llm_prompt)

    try:
        response = clean_json(response)
        data = json.loads(response)

        # validation layer (very important)
        if "priority_items" not in data or "item_quantities" not in data:
            raise ValueError("Invalid format")

        return normalize_output(data)

    except:
        return fallback_parser(prompt)


# 🔧 Clean common LLM issues
def clean_json(text):
    text = text.strip()

    # remove junk before/after JSON
    start = text.find("{")
    end = text.rfind("}") + 1
    text = text[start:end]

    # fix quotes
    text = text.replace("'", '"')

    return text


# 🔧 Ensure structure consistency
def normalize_output(data):
    items = data.get("priority_items", [])
    quantities = data.get("item_quantities", {})

    fixed_quantities = {}

    for item in items:
        if item not in quantities:
            fixed_quantities[item] = {"amount": 1, "unit": "unit"}
        else:
            q = quantities[item]

            amount = q.get("amount", 1)
            unit = q.get("unit", "unit")

            fixed_quantities[item] = {
                "amount": amount,
                "unit": unit
            }

    return {
        "budget": data.get("budget", None),
        "priority_items": items,
        "item_quantities": fixed_quantities
    }


# 🔧 Fallback if LLM fails
def fallback_parser(prompt):
    items = []

    # basic split fallback
    parts = prompt.replace(",", " and ").split("and")

    for p in parts:
        name = p.strip()
        if name:
            items.append(name)

    quantities = {
        item: {"amount": 1, "unit": "unit"}
        for item in items
    }

    return {
        "budget": None,
        "priority_items": items,
        "item_quantities": quantities
    }