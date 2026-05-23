"""
agents/selector_agent.py

Product selection orchestrator.

Selection pipeline (in order of preference):
  1. Deterministic ranking via product_ranker (no LLM cost)
  2. High-confidence fast-path: if score gap is clear, return immediately
  3. LLM disambiguation: structured JSON prompt over top-K candidates
  4. Hard fallback: return top-ranked candidate if LLM fails

API surface intentionally kept minimal.
Only `select_best_product` and `choose_best_product` (compat alias) are public.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from agents.product_ranker import ScoredProduct, rank_products
from config import CONFIG
from llm_client import send_prompt_to_llm
from memory import get_preferred_brand

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────────────────────

def select_best_product(
    item: str,
    products: List[dict],
    preferred_brand: Optional[str] = None,
) -> Optional[dict]:
    """
    Choose the best product for `item` from `products`.

    Args:
        item:            User's item query (e.g. "whole milk").
        products:        Raw scraper dicts [{name, price, card, ...}].
        preferred_brand: Optional brand preference; boosts matching products.

    Returns:
        The selected product dict (with 'card' locator intact), or None.
    """
    if not products:
        logger.warning("select_best_product: empty product list for '%s'", item)
        return None

    logger.info(
        "=== Selecting product for '%s' | %d candidates | preferred='%s' ===",
        item, len(products), preferred_brand or "none",
    )

    # ── Stage 1: Deterministic multi-factor ranking ──────────────────────────
    ranked = rank_products(
        query=item,
        products=products,
        preferred_brand=preferred_brand,
        weights=CONFIG.scoring,
        max_candidates=CONFIG.max_candidates,
        dedup_threshold=CONFIG.dedup_similarity_threshold,
    )

    if not ranked:
        logger.error("Ranker returned empty list for '%s'; returning raw[0]", item)
        return products[0]

    top = ranked[0]

    # ── Stage 2: High-confidence fast path ──────────────────────────────────
    if top.confidence_gap >= CONFIG.confidence_gap_threshold:
        logger.info(
            "Fast path: gap=%.3f >= threshold=%.3f -> '%s'",
            top.confidence_gap,
            CONFIG.confidence_gap_threshold,
            top.features.name,
        )
        return top.product

    # ── Stage 3: LLM disambiguation ─────────────────────────────────────────
    logger.info(
        "Ambiguous top candidates (gap=%.3f < %.3f); invoking LLM",
        top.confidence_gap,
        CONFIG.confidence_gap_threshold,
    )

    llm_pick = _llm_disambiguate(item, ranked[: CONFIG.top_k_for_llm])

    if llm_pick is not None:
        return llm_pick

    # ── Stage 4: Hard fallback ───────────────────────────────────────────────
    logger.info("LLM fallback failed; using top-ranked: '%s'", top.features.name)
    return top.product


def choose_best_product(item: str, products: List[dict]) -> Optional[dict]:
    """
    Backward-compatible alias for `select_best_product`.

    Automatically resolves the preferred brand from purchase history.
    Called directly by BlinkitBot and ZeptoBot.
    """
    preferred = get_preferred_brand(item)
    return select_best_product(item, products, preferred_brand=preferred)


# ──────────────────────────────────────────────────────────────
#  LLM Disambiguation (internal)
# ──────────────────────────────────────────────────────────────

def _build_disambiguation_prompt(item: str, candidates: List[ScoredProduct]) -> str:
    """
    Build a concise, structured LLM prompt that sends full product context
    (name, price, size, brand) rather than just product names.
    Requests JSON output to enable reliable parsing.
    """
    lines = []
    for i, sp in enumerate(candidates):
        f = sp.features
        if f.size_base and f.size_unit:
            size_str = f"{f.size_base:.0f}{f.size_unit}"
            ppu_str = (
                f"Rs{f.price_per_unit:.2f}/{f.size_unit}"
                if f.price_per_unit
                else "?"
            )
        else:
            size_str = "unknown"
            ppu_str = "?"

        lines.append(
            f'{i}: "{f.name}" | Rs{f.price} | size={size_str} | '
            f'value={ppu_str} | brand="{f.brand}"'
        )

    options_block = "\n".join(lines)

    return (
        'You are a grocery shopping assistant helping a user in India.\n'
        f'The user wants to buy: "{item}"\n\n'
        'Choose the single best product. Prefer: correct product type, '
        'good value for money, reputable brand, appropriate size.\n'
        'Avoid: wrong category, unrelated variants, ultra-premium items '
        'the user did not ask for.\n\n'
        f'Candidates (pre-ranked by score, index 0 = current best guess):\n'
        f'{options_block}\n\n'
        'Respond ONLY with valid JSON. No markdown, no explanation.\n'
        'Format: {"selected_index": <int>, "reason": "<10 words max>"}'
    )


def _llm_disambiguate(
    item: str,
    candidates: List[ScoredProduct],
) -> Optional[dict]:
    """
    Call LLM to disambiguate between close-scoring candidates.
    Returns the selected product dict, or None on any failure.

    Failures are logged but never raised — the caller always has a fallback.
    """
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
        logger.error("LLM call raised exception: %s", exc)
        return None

    if not response:
        logger.warning("LLM returned empty response for '%s'", item)
        return None

    return _parse_llm_response(response, candidates, item)


def _parse_llm_response(
    response: str,
    candidates: List[ScoredProduct],
    item: str,
) -> Optional[dict]:
    """
    Parse the LLM's JSON response and return the chosen product dict.

    Strips markdown fences if present. Returns None on any parse failure
    so the caller can fall back gracefully.
    """
    try:
        cleaned = response.strip()
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
            chosen = candidates[idx]
            logger.info(
                "LLM chose index %d: '%s' (reason: %s)",
                idx, chosen.features.name, reason,
            )
            return chosen.product

        logger.warning(
            "LLM returned out-of-range index %d (have %d candidates) for '%s'",
            idx, len(candidates), item,
        )
        return None

    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.warning(
            "Failed to parse LLM response for '%s': %s | raw: '%s'",
            item, exc, response[:120],
        )
        return None
