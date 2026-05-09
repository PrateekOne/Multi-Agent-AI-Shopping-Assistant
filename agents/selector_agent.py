from llm_client import send_prompt_to_llm


BLOCKED_VARIANTS = [
    "curd",
    "greek"
]


def choose_best_product(item, products):
    if not products:
        return None

    item_lower = item.lower()

    filtered = []

    for p in products:
        name = p["name"].lower()

        if is_invalid_variant(item_lower, name):
            continue

        score = calculate_match_score(item_lower, name)

        filtered.append({
            "product": p,
            "score": score
        })

    if not filtered:
        filtered = [
            {
                "product": p,
                "score": 0
            }
            for p in products[:6]
        ]

    filtered.sort(
        key=lambda x: (-x["score"], x["product"]["price"])
    )

    top_products = [x["product"] for x in filtered[:6]]

    exact = try_exact_match(item_lower, top_products)

    if exact:
        return exact

    llm_choice = llm_select(item, top_products)

    if llm_choice:
        return llm_choice

    return top_products[0]


def calculate_match_score(target, candidate):
    target_words = target.split()
    candidate_words = candidate.split()

    score = 0

    for word in target_words:
        if word in candidate_words:
            score += 3

        elif word in candidate:
            score += 1

    if target in candidate:
        score += 10

    return score


def is_invalid_variant(target, candidate):
    if "milk" in target:
        for bad in BLOCKED_VARIANTS:
            if bad in candidate:
                return True

    return False


def try_exact_match(target, products):
    for p in products:
        name = p["name"].lower()

        if target in name:
            return p

    return None


def llm_select(item, products):
    names = [p["name"] for p in products]

    prompt = f"""
Pick the BEST matching product for: {item}

Return ONLY one exact product name.

Rules:
- Prefer exact product type
- Avoid unrelated variants
- Avoid different dairy products
- Avoid premium/protein/cream variants

Options:
{names}
"""

    response = send_prompt_to_llm(prompt)

    if not response:
        return None

    response = clean(response)

    for p in products:
        if response.lower() in p["name"].lower():
            return p

    return None


def clean(text):
    text = text.strip()
    text = text.replace('"', "")
    text = text.replace("\n", "")
    return text


def select_best_product(item, products):
    return choose_best_product(item, products)