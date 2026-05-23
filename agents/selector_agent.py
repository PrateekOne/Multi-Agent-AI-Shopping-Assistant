import json
import logging
from typing import List, Optional

from agents.product_ranker import ScoredProduct, rank_products
from config import CONFIG
from llm_client import send_prompt_to_llm
from memory import get_preferred_brand

logger = logging.getLogger(__name__)


def select_best_product(
    item: str,
    products: List[dict],
    preferred_brand: Optional[str] = None,
) -> Optional[dict]:
    if not products:
        logger.warning("select_best_product: empty list for '%s'", item)
        return None

    logger.info("Selecting product for '%s' | %d candidates | preferred='%s'",
                item, len(products), preferred_brand or "none")

    ranked = rank_products(
        query=item,
        products=products,
        preferred_brand=preferred_brand,
        weights=CONFIG.scoring,
        max_candidates=CONFIG.max_candidates,
        dedup_threshold=CONFIG.dedup_similarity_threshold,
    )

    if not ranked:
        logger.error("Ranker returned nothing for '%s'; falling back to first result", item)
        return products[0]

    top = ranked[0]

    # If the gap between first and second place is large enough we trust the
    # ranker and skip the LLM call entirely to save tokens
    if top.confidence_gap >= CONFIG.confidence_gap_threshold:
        logger.info("Confident pick (gap=%.3f): '%s'", top.confidence_gap, top.features.name)
        return top.product

    # Too close to call — ask the LLM to break the tie
    logger.info("Scores too close (gap=%.3f); asking LLM to disambiguate", top.confidence_gap)
    llm_pick = _llm_disambiguate(item, ranked[:CONFIG.top_k_for_llm])

    if llm_pick is not None:
        return llm_pick

    # LLM failed or timed out — just use the top-ranked result
    logger.info("LLM fallback failed; using top-ranked: '%s'", top.features.name)
    return top.product


def choose_best_product(item: str, products: List[dict]) -> Optional[dict]:
    # Public entry point used by both bots — pulls preferred brand from memory
    preferred = get_preferred_brand(item)
    return select_best_product(item, products, preferred_brand=preferred)


def _build_disambiguation_prompt(item: str, candidates: List[ScoredProduct]) -> str:
    lines = []
    for i, sp in enumerate(candidates):
        f = sp.features
        if f.size_base and f.size_unit:
            size_str = f"{f.size_base:.0f}{f.size_unit}"
            ppu_str = f"Rs{f.price_per_unit:.2f}/{f.size_unit}" if f.price_per_unit else "?"
        else:
            size_str = "unknown"
            ppu_str = "?"
        lines.append(
            f'{i}: "{f.name}" | Rs{f.price} | size={size_str} | value={ppu_str} | brand="{f.brand}"'
        )

    return (
        'You are a grocery shopping assistant helping a user in India.\n'
        f'The user wants to buy: "{item}"\n\n'
        'Pick the single best product. Prefer correct type, good value, reputable brand.\n'
        'Avoid wrong category or unrelated variants.\n\n'
        f'Candidates (index 0 = current best guess):\n'
        + "\n".join(lines) + "\n\n"
        'Reply ONLY with valid JSON. No markdown.\n'
        'Format: {"selected_index": <int>, "reason": "<10 words max>"}'
    )


def _llm_disambiguate(item: str, candidates: List[ScoredProduct]) -> Optional[dict]:
    if not candidates:
        return None

    prompt = _build_disambiguation_prompt(item, candidates)

    try:
        response = send_prompt_to_llm(
            prompt,
            max_tokens=CONFIG.llm.max_tokens_select,
            temperature=CONFIG.llm.temperature_select,
        )
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return None

    if not response:
        logger.warning("LLM returned empty response for '%s'", item)
        return None

    return _parse_llm_response(response, candidates, item)


def _parse_llm_response(
    response: str, candidates: List[ScoredProduct], item: str
) -> Optional[dict]:
    try:
        cleaned = response.strip()
        # Strip markdown code fences if the LLM wrapped the JSON in them
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            cleaned = parts[1] if len(parts) > 1 else cleaned
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        idx = int(data.get("selected_index", -1))
        reason = data.get("reason", "no reason given")

        if 0 <= idx < len(candidates):
            logger.info("LLM chose index %d: '%s' (%s)", idx, candidates[idx].features.name, reason)
            return candidates[idx].product

        logger.warning("LLM index %d out of range for '%s'", idx, item)
        return None

    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.warning("Could not parse LLM response for '%s': %s | raw='%s'", item, exc, response[:120])
        return None
