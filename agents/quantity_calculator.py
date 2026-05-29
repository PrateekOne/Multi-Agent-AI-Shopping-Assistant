import logging
import math

from agents.product_ranker import extract_features

logger = logging.getLogger(__name__)

MAX_UNITS = 10

_REQUEST_UNIT_MAP = {
    "ml":      ("ml",  1.0),
    "l":       ("ml",  1000.0),
    "ltr":     ("ml",  1000.0),
    "litre":   ("ml",  1000.0),
    "liter":   ("ml",  1000.0),
    "litres":  ("ml",  1000.0),
    "liters":  ("ml",  1000.0),
    "g":       ("g",   1.0),
    "gm":      ("g",   1.0),
    "gms":     ("g",   1.0),
    "gram":    ("g",   1.0),
    "grams":   ("g",   1.0),
    "kg":      ("g",   1000.0),
    "kgs":     ("g",   1000.0),
    "pcs":     ("ct",  1.0),
    "pc":      ("ct",  1.0),
    "piece":   ("ct",  1.0),
    "pieces":  ("ct",  1.0),
    "pack":    ("ct",  1.0),
    "packet":  ("ct",  1.0),
    "packets": ("ct",  1.0),
    "unit":    ("ct",  1.0),
    "units":   ("ct",  1.0),
}

_COUNT_UNITS = {"pcs", "pc", "piece", "pieces", "pack", "packet", "packets", "unit", "units"}


def calculate_units_needed(requested_amount, requested_unit: str, product_name: str) -> int:
    """
    Work out how many product packs to add to the cart.

    Examples:
      requested 2 litre, product 500ml   ->  ceil(2000 / 500)  = 4 packs
      requested 2 litre, product 1L      ->  ceil(2000 / 1000) = 2 packs
      requested 1 kg,    product 500g    ->  ceil(1000 / 500)  = 2 packs
      requested 6 pcs,   product 6-pack  ->  ceil(6 / 6)       = 1 pack
      requested 6 pcs,   product 12-pack ->  ceil(6 / 12)      = 1 pack
      requested 3 units, unknown size    ->  3 packs (direct count)
      requested 2 litre, no size in name ->  1 pack (safe fallback)
    """
    try:
        amount = float(requested_amount) if requested_amount else 1.0
    except (TypeError, ValueError):
        amount = 1.0

    unit_lower = (requested_unit or "unit").lower().strip()

    if unit_lower in _COUNT_UNITS:
        # User asked for N items/packs. If the product is a multipack (e.g. 6-pack
        # of eggs), divide so we don't buy 6 boxes of 6 when user asked for 6 eggs.
        feats = extract_features({"name": product_name, "price": 0})
        if feats.size_base and feats.size_base > 1 and feats.size_unit == "ct":
            units_needed = math.ceil(amount / feats.size_base)
            result = max(1, min(units_needed, MAX_UNITS))
            logger.info(
                "Quantity calc: %d items requested / %d per pack = %d pack(s) of '%s'",
                int(amount), int(feats.size_base), result, product_name[:50],
            )
            return result
        # Single-unit product or unknown pack size — use the count directly
        return max(1, min(int(amount), MAX_UNITS))

    req_mapping = _REQUEST_UNIT_MAP.get(unit_lower)
    if req_mapping is None:
        logger.debug("Unknown unit '%s'; using raw amount %s as count", unit_lower, amount)
        return max(1, min(int(amount), MAX_UNITS))

    req_base_unit, req_multiplier = req_mapping
    requested_in_base = amount * req_multiplier

    feats = extract_features({"name": product_name, "price": 0})

    if feats.size_base is None:
        # Product name has no size info — we can't calculate packs.
        # Safe default is 1 so we don't over-buy.
        logger.debug("No size in '%s'; defaulting to 1 pack", product_name[:50])
        return 1

    if feats.size_base > 0 and feats.size_unit == req_base_unit:
        units_needed = math.ceil(requested_in_base / feats.size_base)
        result = max(1, min(units_needed, MAX_UNITS))
        logger.info(
            "Quantity calc: %.0f%s requested / %.0f%s per pack = %d pack(s) of '%s'",
            requested_in_base, req_base_unit,
            feats.size_base, feats.size_unit,
            result, product_name[:50],
        )
        return result

    # Unit types don't match (e.g. user wants ml but product measured in g)
    logger.debug(
        "Unit mismatch: requested %s but product is in %s for '%s'; defaulting to 1",
        req_base_unit, feats.size_unit, product_name[:50],
    )
    return 1
