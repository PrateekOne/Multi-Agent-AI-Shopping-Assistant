from llm_client import send_prompt_to_llm


def choose_best_product(item, products):
    if not products:
        return None

    # limit options for small LLM
    filtered = products[:6]

    names = [p["name"] for p in filtered]

    prompt = f"""
Pick the best product for: {item}

Return ONLY one exact product name from the list.
No explanation.

Rules:
- Prefer well-known brands
- Prefer exact match
- Avoid unrelated items

Options:
{names}
"""

    response = send_prompt_to_llm(prompt)

    if not response:
        return filtered[0]

    chosen = clean_response(response)

    # match with real product
    for p in filtered:
        if chosen.lower() in p["name"].lower():
            return p

    # fallback
    return filtered[0]


def clean_response(text):
    text = text.strip()
    text = text.replace("\n", "")
    text = text.replace('"', "")
    return text


# 🔥 IMPORTANT: backward compatibility (fixes your error)
def select_best_product(item, products):
    return choose_best_product(item, products)