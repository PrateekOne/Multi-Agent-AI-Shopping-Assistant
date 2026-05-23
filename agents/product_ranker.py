"""
agents/product_ranker.py

Intelligent multi-factor product ranking engine.

Ranking pipeline:
  1. Feature extraction  — parse brand, size, unit, price-per-unit from name
  2. Variant filtering   — block wrong-category products via generalized blocklist
  3. Relevance scoring   — F1 of token overlap + substring bonus
  4. Value scoring       — normalized price-per-unit efficiency
  5. Brand scoring       — quality tier + user preference match
  6. Weighted aggregation
  7. Sort descending
  8. Deduplication       — Jaccard similarity suppression of near-identical listings

Design principles:
  - No LLM calls here. This module is purely deterministic.
  - All scores are in [0.0, 1.0] before weighting.
  - The 'card' Playwright locator in product dicts is passed through untouched.
  - Safe to call with empty or malformed product lists.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from config import (
    QUALITY_BRANDS_TIER1,
    QUALITY_BRANDS_TIER2,
    VARIANT_BLOCKLIST,
    ScoringWeights,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────────────────────

STOPWORDS: frozenset = frozenset({
    "the", "a", "an", "and", "or", "with", "for", "of", "in",
    "by", "from", "fresh", "new", "best", "top", "natural", "pure",
    "original", "classic", "premium",
})

# Regex: numeric size + unit anywhere in a product name string
_SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(ml|l\b|ltr|litre|litres|g\b|gm|gms|gram|grams|kg|kgs"
    r"|pcs|pc|piece|pieces|pack|nos|unit|units)",
    re.IGNORECASE,
)

# Maps each unit token the regex can capture → (base_unit_label, multiplier)
_UNIT_MAP: Dict[str, Tuple[str, float]] = {
    "ml":      ("ml",    1.0),
    "l":       ("ml", 1000.0),
    "ltr":     ("ml", 1000.0),
    "litre":   ("ml", 1000.0),
    "litres":  ("ml", 1000.0),
    "g":       ("g",     1.0),
    "gm":      ("g",     1.0),
    "gms":     ("g",     1.0),
    "gram":    ("g",     1.0),
    "grams":   ("g",     1.0),
    "kg":      ("g",  1000.0),
    "kgs":     ("g",  1000.0),
    "pcs":     ("ct",    1.0),
    "pc":      ("ct",    1.0),
    "piece":   ("ct",    1.0),
    "pieces":  ("ct",    1.0),
    "pack":    ("ct",    1.0),
    "nos":     ("ct",    1.0),
    "unit":    ("ct",    1.0),
    "units":   ("ct",    1.0),
}


# ──────────────────────────────────────────────────────────────
#  Data Structures
# ──────────────────────────────────────────────────────────────

@dataclass
class ProductFeatures:
    """Structured, normalized view of a single raw product dict."""
    name: str
    price: float
    tokens: frozenset          # meaningful word tokens from name
    brand: str                 # detected brand or leading token
    size_base: Optional[float] # size in base unit (ml / g / count)
    size_unit: Optional[str]   # "ml" | "g" | "ct"
    price_per_unit: Optional[float]  # price / size_base


@dataclass
class ScoredProduct:
    """A product annotated with its dimensional scores and weighted total."""
    product: dict              # original dict — preserves 'card' Playwright locator
    features: ProductFeatures
    relevance: float = 0.0
    value: float = 0.0
    brand: float = 0.0
    total: float = 0.0
    confidence_gap: float = 0.0  # gap to the next-best candidate (set post-sort)


# ──────────────────────────────────────────────────────────────
#  Feature Extraction
# ──────────────────────────────────────────────────────────────

def _tokenize(text: str) -> frozenset:
    """Lowercase, strip punctuation, split, remove stopwords and single chars."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return frozenset(
        w for w in cleaned.split()
        if w not in STOPWORDS and len(w) > 1
    )


def _parse_size(name: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Extract the first size measurement from a product name.

    Returns (size_in_base_unit, base_unit_label) or (None, None).
    Examples:
      "Amul Taaza 500ml"  → (500.0, "ml")
      "Rice 5kg"          → (5000.0, "g")
      "Eggs 6 Pcs"        → (6.0, "ct")
    """
    match = _SIZE_RE.search(name)
    if not match:
        return None, None

    value = float(match.group(1))
    unit_key = match.group(2).lower()
    mapping = _UNIT_MAP.get(unit_key)

    if mapping is None:
        return None, None

    base_unit, multiplier = mapping
    return value * multiplier, base_unit


def _detect_brand(name_lower: str) -> str:
    """
    Return the best-guess brand for a product name.
    Checks tier-1 brands first (higher quality signal), then tier-2,
    then falls back to the first meaningful token.
    """
    for brand in QUALITY_BRANDS_TIER1:
        if brand in name_lower:
            return brand

    for brand in QUALITY_BRANDS_TIER2:
        if brand in name_lower:
            return brand

    # Heuristic fallback: first token that is ≥ 3 chars, not a stopword
    for tok in name_lower.split():
        if tok not in STOPWORDS and len(tok) >= 3 and not tok.isdigit():
            return tok

    return ""


def extract_features(product: dict) -> ProductFeatures:
    """Build a ProductFeatures from a raw scraper product dict."""
    name: str = product.get("name", "")
    price: float = float(product.get("price", 0.0))
    name_lower = name.lower()

    size_base, size_unit = _parse_size(name)
    price_per_unit = (price / size_base) if (size_base and size_base > 0) else None

    return ProductFeatures(
        name=name,
        price=price,
        tokens=_tokenize(name),
        brand=_detect_brand(name_lower),
        size_base=size_base,
        size_unit=size_unit,
        price_per_unit=price_per_unit,
    )


# ──────────────────────────────────────────────────────────────
#  Variant Filtering
# ──────────────────────────────────────────────────────────────

def _get_blocked_terms(query: str) -> List[str]:
    """Return the blocklist for the category matched in the query, if any."""
    query_lower = query.lower()
    for category_key, blocked_terms in VARIANT_BLOCKLIST.items():
        if category_key in query_lower:
            return blocked_terms
    return []


def _is_blocked(product_name_lower: str, blocked_terms: List[str]) -> bool:
    return any(term in product_name_lower for term in blocked_terms)


# ──────────────────────────────────────────────────────────────
#  Scoring Dimensions
# ──────────────────────────────────────────────────────────────

def score_relevance(query: str, features: ProductFeatures) -> float:
    """
    Token-level F1 between query and product name, with bonuses.

    - Recall:    fraction of query words found in product name
    - Precision: fraction of product words that are relevant to query
    - F1:        harmonic mean — penalises products that are too broad or too narrow
    - Substring bonus (+0.20): exact query phrase appears in product name
    - Full coverage bonus (+0.10): every query word is covered

    Returns a value in [0.0, 1.0].
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.5  # can't score without a query

    product_tokens = features.tokens
    if not product_tokens:
        return 0.0

    overlap = query_tokens & product_tokens
    recall = len(overlap) / len(query_tokens)
    precision = len(overlap) / len(product_tokens)

    f1 = (
        2 * recall * precision / (recall + precision)
        if (recall + precision) > 0
        else 0.0
    )

    substring_bonus = 0.20 if query.lower() in features.name.lower() else 0.0
    full_match_bonus = 0.10 if query_tokens <= product_tokens else 0.0

    return min(1.0, f1 + substring_bonus + full_match_bonus)


def score_value(
    features: ProductFeatures,
    all_features: List[ProductFeatures],
) -> float:
    """
    Normalized inverse price-per-unit score.

    Strategy:
      1. Try price-per-unit comparison within the same unit class (ml, g, ct).
         This correctly handles "500ml ₹25 vs 1L ₹40" (1L is better value).
      2. If units are unavailable or incompatible, fall back to raw price normalization.
      3. If only one product, return 0.5 (neutral — no relative comparison possible).

    Best value → 1.0. Worst value → 0.0.
    """
    # Strategy 1: price-per-unit within same base unit
    if features.size_unit and features.price_per_unit is not None:
        ppus = [
            f.price_per_unit
            for f in all_features
            if f.size_unit == features.size_unit and f.price_per_unit is not None
        ]
        if len(ppus) >= 2:
            min_ppu, max_ppu = min(ppus), max(ppus)
            spread = max_ppu - min_ppu
            if spread > 1e-9:
                return 1.0 - (features.price_per_unit - min_ppu) / spread
            return 0.5  # all same price-per-unit

    # Strategy 2: raw price normalization (lower is better)
    prices = [f.price for f in all_features if f.price > 0]
    if len(prices) < 2:
        return 0.5
    min_p, max_p = min(prices), max(prices)
    spread = max_p - min_p
    if spread < 1e-9:
        return 0.5
    return 1.0 - (features.price - min_p) / spread


def score_brand(
    features: ProductFeatures,
    preferred_brand: Optional[str],
) -> float:
    """
    Brand quality score based on recognition tier and user preference.

    Score ladder:
      1.00 — Product matches user's preferred brand from purchase history
      0.85 — Tier-1 quality brand (flagship FMCG)
      0.65 — Tier-2 quality brand (well-known regional/snack)
      0.35 — Unknown or unrecognized brand (no penalty, just no boost)
    """
    name_lower = features.name.lower()

    if preferred_brand and preferred_brand.lower() in name_lower:
        return 1.0

    if any(b in name_lower for b in QUALITY_BRANDS_TIER1):
        return 0.85

    if any(b in name_lower for b in QUALITY_BRANDS_TIER2):
        return 0.65

    return 0.35


# ──────────────────────────────────────────────────────────────
#  Deduplication
# ──────────────────────────────────────────────────────────────

def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    union_size = len(a | b)
    return len(a & b) / union_size if union_size > 0 else 0.0


def deduplicate(
    scored: List[ScoredProduct],
    similarity_threshold: float = 0.80,
) -> List[ScoredProduct]:
    """
    Remove near-duplicate product listings from the ranked list.

    Two products are considered duplicates if their name-token Jaccard
    similarity exceeds `similarity_threshold`. When duplicates are found,
    the lower-scoring one is dropped (list is already sorted by score desc).

    Typical use case: same product listed twice with slightly different
    descriptions or prices due to scraper pagination.
    """
    kept: List[ScoredProduct] = []

    for candidate in scored:
        is_duplicate = False
        for existing in kept:
            sim = _jaccard(candidate.features.tokens, existing.features.tokens)
            if sim >= similarity_threshold:
                is_duplicate = True
                logger.debug(
                    "Dedup: dropped '%s' (sim=%.2f with '%s')",
                    candidate.features.name[:60],
                    sim,
                    existing.features.name[:60],
                )
                break
        if not is_duplicate:
            kept.append(candidate)

    return kept


# ──────────────────────────────────────────────────────────────
#  Main Entry Point
# ──────────────────────────────────────────────────────────────

def rank_products(
    query: str,
    products: List[dict],
    preferred_brand: Optional[str] = None,
    weights: Optional[ScoringWeights] = None,
    max_candidates: int = 10,
    dedup_threshold: float = 0.80,
) -> List[ScoredProduct]:
    """
    Full ranking pipeline. Returns products sorted by weighted score (best first).

    Args:
        query:           User's item query string (e.g. "whole milk 1 litre").
        products:        Raw product dicts from scraper — [{name, price, card, ...}].
        preferred_brand: Brand from purchase history; scores 1.0 if matched.
        weights:         ScoringWeights config (uses defaults if None).
        max_candidates:  Cap on how many raw products enter the pipeline.
        dedup_threshold: Jaccard threshold above which two products are duplicates.

    Returns:
        List of ScoredProduct, sorted descending by total score.
        The 'product' field on each ScoredProduct is the original dict
        (including the 'card' Playwright locator) so bots can use it directly.
    """
    if not products:
        return []

    if weights is None:
        weights = ScoringWeights()

    logger.info(
        "Ranking %d products for query='%s' | preferred_brand=%s",
        min(len(products), max_candidates), query, preferred_brand or "none",
    )

    blocked_terms = _get_blocked_terms(query)
    candidates = products[:max_candidates]

    # ── Step 1: Feature extraction + variant filtering ──────────────────────
    featured: List[Tuple[dict, ProductFeatures]] = []
    for p in candidates:
        feats = extract_features(p)
        if _is_blocked(feats.name.lower(), blocked_terms):
            logger.debug("Blocked: '%s'", feats.name)
            continue
        featured.append((p, feats))

    if not featured:
        # All candidates were blocked — use unfiltered to avoid returning nothing
        logger.warning(
            "All products blocked for query '%s'; reverting to unfiltered list.", query
        )
        featured = [(p, extract_features(p)) for p in candidates]

    all_features = [f for _, f in featured]

    # ── Step 2: Score each candidate ────────────────────────────────────────
    scored: List[ScoredProduct] = []
    for product, feats in featured:
        rel = score_relevance(query, feats)
        val = score_value(feats, all_features)
        brd = score_brand(feats, preferred_brand)

        total = (
            weights.relevance * rel
            + weights.value * val
            + weights.brand * brd
        )

        scored.append(ScoredProduct(
            product=product,
            features=feats,
            relevance=rel,
            value=val,
            brand=brd,
            total=total,
        ))

        logger.debug(
            "  [%.3f] %-52s  rel=%.2f  val=%.2f  brand=%.2f",
            total, feats.name[:52], rel, val, brd,
        )

    # ── Step 3: Sort descending by total score ───────────────────────────────
    scored.sort(key=lambda x: x.total, reverse=True)

    # ── Step 4: Deduplicate ──────────────────────────────────────────────────
    scored = deduplicate(scored, dedup_threshold)

    # ── Step 5: Compute confidence gap on the top candidate ─────────────────
    if len(scored) >= 2:
        scored[0].confidence_gap = scored[0].total - scored[1].total
    elif len(scored) == 1:
        scored[0].confidence_gap = scored[0].total  # sole candidate — fully confident

    if scored:
        logger.info(
            "Top pick: '%s' | total=%.3f | gap=%.3f | rel=%.2f | val=%.2f | brand=%.2f",
            scored[0].features.name[:60],
            scored[0].total,
            scored[0].confidence_gap,
            scored[0].relevance,
            scored[0].value,
            scored[0].brand,
        )

    return scored
