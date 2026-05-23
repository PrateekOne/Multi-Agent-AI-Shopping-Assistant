import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from config import (
    CONFIG,
    QUALITY_BRANDS_TIER1,
    QUALITY_BRANDS_TIER2,
    VARIANT_BLOCKLIST,
    ScoringWeights,
)

logger = logging.getLogger(__name__)


# Words that appear in almost every product name and carry no useful signal
STOPWORDS: frozenset = frozenset({
    "the", "a", "an", "and", "or", "with", "for", "of", "in",
    "by", "from", "fresh", "new", "best", "top", "natural", "pure",
    "original", "classic", "premium",
})

# Matches things like "500ml", "1 kg", "6 pcs" anywhere in a product name
_SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(ml|l\b|ltr|litre|litres|g\b|gm|gms|gram|grams|kg|kgs"
    r"|pcs|pc|piece|pieces|pack|nos|unit|units)",
    re.IGNORECASE,
)

# Converts each unit string to a common base unit so sizes are comparable
_UNIT_MAP: Dict[str, Tuple[str, float]] = {
    "ml": ("ml", 1.0), "l": ("ml", 1000.0), "ltr": ("ml", 1000.0),
    "litre": ("ml", 1000.0), "litres": ("ml", 1000.0),
    "g": ("g", 1.0), "gm": ("g", 1.0), "gms": ("g", 1.0),
    "gram": ("g", 1.0), "grams": ("g", 1.0),
    "kg": ("g", 1000.0), "kgs": ("g", 1000.0),
    "pcs": ("ct", 1.0), "pc": ("ct", 1.0), "piece": ("ct", 1.0),
    "pieces": ("ct", 1.0), "pack": ("ct", 1.0), "nos": ("ct", 1.0),
    "unit": ("ct", 1.0), "units": ("ct", 1.0),
}


@dataclass
class ProductFeatures:
    name: str
    price: float
    tokens: frozenset
    brand: str
    size_base: Optional[float]   # size converted to base unit (ml / g / count)
    size_unit: Optional[str]     # "ml", "g", or "ct"
    price_per_unit: Optional[float]


@dataclass
class ScoredProduct:
    product: dict                # original dict including the Playwright 'card' locator
    features: ProductFeatures
    relevance: float = 0.0
    value: float = 0.0
    brand: float = 0.0
    total: float = 0.0
    confidence_gap: float = 0.0  # difference in score between #1 and #2


def _normalize_text(text: str) -> str:
    # Strip apostrophes before replacing punctuation so "Lay's" becomes "lays"
    # not "lay" + "s". Without this, searching "lays" never matches Lay's products.
    text = text.lower()
    text = text.replace("'", "").replace("\u2019", "").replace("\u2018", "")
    text = re.sub(r"[^\w\s]", " ", text)
    return text


def _tokenize(text: str) -> frozenset:
    cleaned = _normalize_text(text)
    return frozenset(w for w in cleaned.split() if w not in STOPWORDS and len(w) > 1)


def _parse_size(name: str) -> Tuple[Optional[float], Optional[str]]:
    # Pull out the first size measurement and convert to base unit
    # e.g. "5kg" -> (5000.0, "g"),  "500ml" -> (500.0, "ml")
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
    # Check tier-1 first since they carry a stronger quality signal
    for brand in QUALITY_BRANDS_TIER1:
        if brand in name_lower:
            return brand
    for brand in QUALITY_BRANDS_TIER2:
        if brand in name_lower:
            return brand
    # Fallback: use the first real word in the name as a proxy for brand
    for tok in name_lower.split():
        if tok not in STOPWORDS and len(tok) >= 3 and not tok.isdigit():
            return tok
    return ""


def extract_features(product: dict) -> ProductFeatures:
    name: str = product.get("name", "")
    price: float = float(product.get("price", 0.0))
    size_base, size_unit = _parse_size(name)
    price_per_unit = (price / size_base) if (size_base and size_base > 0) else None
    return ProductFeatures(
        name=name,
        price=price,
        tokens=_tokenize(name),
        brand=_detect_brand(name.lower()),
        size_base=size_base,
        size_unit=size_unit,
        price_per_unit=price_per_unit,
    )


def _get_blocked_terms(query: str) -> List[str]:
    query_lower = query.lower()
    for category_key, blocked_terms in VARIANT_BLOCKLIST.items():
        if category_key in query_lower:
            return blocked_terms
    return []


def _is_blocked(product_name_lower: str, blocked_terms: List[str]) -> bool:
    return any(term in product_name_lower for term in blocked_terms)


def score_relevance(query: str, features: ProductFeatures) -> float:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.5
    product_tokens = features.tokens
    if not product_tokens:
        return 0.0

    overlap = query_tokens & product_tokens
    recall = len(overlap) / len(query_tokens)
    precision = len(overlap) / len(product_tokens)
    f1 = (2 * recall * precision / (recall + precision)) if (recall + precision) > 0 else 0.0

    # Bonus if the full query phrase appears verbatim in the product name
    substring_bonus = 0.20 if _normalize_text(query) in _normalize_text(features.name) else 0.0
    full_match_bonus = 0.10 if query_tokens <= product_tokens else 0.0

    return min(1.0, f1 + substring_bonus + full_match_bonus)


def score_value(features: ProductFeatures, all_features: List[ProductFeatures]) -> float:
    # Compare price-per-unit within the same unit class first (e.g. all "ml" products)
    # This handles "500ml @ Rs25 vs 1L @ Rs40" correctly — the 1L is better value
    if features.size_unit and features.price_per_unit is not None:
        ppus = [
            f.price_per_unit for f in all_features
            if f.size_unit == features.size_unit and f.price_per_unit is not None
        ]
        if len(ppus) >= 2:
            min_ppu, max_ppu = min(ppus), max(ppus)
            spread = max_ppu - min_ppu
            if spread > 1e-9:
                return 1.0 - (features.price_per_unit - min_ppu) / spread
            return 0.5

    # Fallback: normalize raw price across the candidate pool
    prices = [f.price for f in all_features if f.price > 0]
    if len(prices) < 2:
        return 0.5
    min_p, max_p = min(prices), max(prices)
    spread = max_p - min_p
    if spread < 1e-9:
        return 0.5
    return 1.0 - (features.price - min_p) / spread


def score_brand(features: ProductFeatures, preferred_brand: Optional[str]) -> float:
    # Score ladder: preferred brand > tier-1 > tier-2 > unknown
    name_lower = features.name.lower()
    if preferred_brand and preferred_brand.lower() in name_lower:
        return 1.0
    if any(b in name_lower for b in QUALITY_BRANDS_TIER1):
        return 0.85
    if any(b in name_lower for b in QUALITY_BRANDS_TIER2):
        return 0.65
    return 0.35


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    union_size = len(a | b)
    return len(a & b) / union_size if union_size > 0 else 0.0


def deduplicate(scored: List[ScoredProduct], similarity_threshold: float = 0.80) -> List[ScoredProduct]:
    # Drop near-duplicate listings — same product scraped twice with slightly
    # different descriptions. Keep the higher-scoring one (list is already sorted).
    kept: List[ScoredProduct] = []
    for candidate in scored:
        is_duplicate = False
        for existing in kept:
            if _jaccard(candidate.features.tokens, existing.features.tokens) >= similarity_threshold:
                is_duplicate = True
                logger.debug("Dedup: dropped '%s'", candidate.features.name[:60])
                break
        if not is_duplicate:
            kept.append(candidate)
    return kept


def rank_products(
    query: str,
    products: List[dict],
    preferred_brand: Optional[str] = None,
    weights: Optional[ScoringWeights] = None,
    max_candidates: int = 10,
    dedup_threshold: float = 0.80,
) -> List[ScoredProduct]:
    if not products:
        return []

    if weights is None:
        weights = ScoringWeights()

    logger.info("Ranking %d products for query='%s'", min(len(products), max_candidates), query)

    blocked_terms = _get_blocked_terms(query)
    candidates = products[:max_candidates]

    # Step 1: extract features and drop products that are the wrong category
    featured: List[Tuple[dict, ProductFeatures]] = []
    for p in candidates:
        feats = extract_features(p)
        if _is_blocked(feats.name.lower(), blocked_terms):
            logger.debug("Blocked: '%s'", feats.name)
            continue
        featured.append((p, feats))

    if not featured:
        # All products were blocked — fall back to unfiltered so we return something
        logger.warning("All products blocked for '%s'; reverting to unfiltered list.", query)
        featured = [(p, extract_features(p)) for p in candidates]

    all_features = [f for _, f in featured]

    # Step 2: score every candidate on three dimensions
    scored: List[ScoredProduct] = []
    for product, feats in featured:
        rel = score_relevance(query, feats)
        val = score_value(feats, all_features)
        brd = score_brand(feats, preferred_brand)
        total = weights.relevance * rel + weights.value * val + weights.brand * brd

        scored.append(ScoredProduct(
            product=product, features=feats,
            relevance=rel, value=val, brand=brd, total=total,
        ))
        logger.debug("[%.3f] %-50s rel=%.2f val=%.2f brand=%.2f", total, feats.name[:50], rel, val, brd)

    # Step 3: remove products that scored zero relevance so they can't
    # accidentally win on brand/value alone (e.g. Britannia beating Lay's)
    min_rel = CONFIG.min_relevance_threshold
    relevant = [s for s in scored if s.relevance >= min_rel]
    if relevant:
        scored = relevant
    else:
        logger.warning("No products passed relevance gate for '%s'; using full list.", query)

    # Step 4: sort best first, then deduplicate near-identical listings
    scored.sort(key=lambda x: x.total, reverse=True)
    scored = deduplicate(scored, dedup_threshold)

    # Step 5: measure how confident we are in the top pick
    if len(scored) >= 2:
        scored[0].confidence_gap = scored[0].total - scored[1].total
    elif len(scored) == 1:
        scored[0].confidence_gap = scored[0].total

    if scored:
        logger.info(
            "Top pick: '%s' | score=%.3f | gap=%.3f",
            scored[0].features.name[:60], scored[0].total, scored[0].confidence_gap,
        )

    return scored
